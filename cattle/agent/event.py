import logging
import os
import re
import sys
import time
import websocket
import base64

from cattle import Config
from cattle import type_manager
from cattle import utils
from cattle.agent import Agent
from cattle.lock import FailedToLock
from cattle.plugins.core.publisher import Publisher
from cattle.concurrency import Queue, Full, Empty, run, spawn


log = logging.getLogger("agent")
_STAMP_TS = None


def _get_event_suffix(agent_id):
    parts = re.split('[a-z]+', agent_id)
    if len(parts) > 1:
        return ';agent=' + parts[1]
    else:
        return ';agent=' + agent_id


def _events_query_string(events, agent_id):
    params = []
    suffix = ''

    if agent_id is not None:
        params.append('agentId=%s' % agent_id)
        suffix = _get_event_suffix(agent_id)

    params.extend(['eventNames=' + event + suffix for event in events])

    qs = '&'.join(params)
    return qs


def _check_ts():
    stamp_file = Config.stamp()
    if not os.path.exists(stamp_file):
        return True

    ts = os.path.getmtime(stamp_file)
    global _STAMP_TS

    if _STAMP_TS is None:
        _STAMP_TS = ts

    return _STAMP_TS == ts


def _should_run(pid):
    if not _check_ts():
        return False

    if pid is None:
        return True
    else:
        return os.path.exists('/proc/%s' % pid)


def _worker(worker_name, queue, ppid):
    try:
        _worker_main(worker_name, queue, ppid)
    except:
        log.exception('%s : Exiting Exception', worker_name)
    finally:
        log.error('%s : Exiting', worker_name)


def _worker_main(worker_name, queue, ppid):
    agent = Agent()
    marshaller = type_manager.get_type(type_manager.MARSHALLER)
    publisher = type_manager.get_type(type_manager.PUBLISHER)
    while True:
        try:
            req = None
            line = queue.get(True, 5)

            req = marshaller.from_string(line)

            utils.log_request(req, log, 'Request: %s', line)

            id = req.id
            start = time.time()
            try:
                utils.log_request(req, log, '%s : Starting request %s for %s',
                                  worker_name, id, req.name)
                resp = agent.execute(req)
                if resp is not None:
                    publisher.publish(resp)
            finally:
                duration = time.time() - start
                utils.log_request(req, log,
                                  '%s : Done request %s for %s [%s] seconds',
                                  worker_name, id, req.name, duration)
        except Empty:
            if not _should_run(ppid):
                break
        except FailedToLock as e:
            log.info("%s for %s", e, req.name)
            if not _should_run(ppid):
                break
        except Exception as e:
            if id is not None:
                log.exception('Error in request : %s', id)
            else:
                log.exception("Unknown error")
            if not _should_run(ppid):
                break

            resp = utils.reply(req)
            if resp is not None:
                resp["transitioning"] = "error"
                resp["transitioningInternalMessage"] = "{0}".format(e)
                publisher.publish(resp)


class EventClient:
    def __init__(self, url, auth=None, workers=20, agent_id=None,
                 queue_depth=Config.queue_depth()):
        if url.endswith("/schemas"):
            url = url[0:len(url)-len("/schemas")]
        self._url = url + "/subscribe"
        self._auth = auth
        self._workers = int(workers)
        self._children = []
        self._agent_id = agent_id
        self._queue = Queue(queue_depth)
        self._ping_queue = Queue(queue_depth)

        type_manager.register_type(type_manager.PUBLISHER,
                                   Publisher(url + "/publish", auth))

    def _start_children(self):
        pid = os.getpid()
        for i in range(self._workers):
            p = spawn(target=_worker, args=('worker{0}'.format(i),
                                            self._queue, pid))
            self._children.append(p)

        p = spawn(target=_worker, args=('ping', self._ping_queue, pid))
        self._children.append(p)

    def run(self, events):
        _check_ts()
        run(self._run, events)

    def _run(self, events):
        ppid = os.environ.get("AGENT_PARENT_PID")
        headers = []

        if self._auth is not None:
            auth_header = 'Authorization: Basic ' + base64.b64encode(
                ('%s:%s' % self._auth).encode('latin1')).strip()
            headers.append(auth_header)

        subscribe_url = self._url.replace('http', 'ws')
        query_string = _events_query_string(events, self._agent_id)
        subscribe_url = subscribe_url + '?' + query_string

        try:
            drops = {
                'drop_count': 0,
                'ping_drop': 0,
            }
            self._start_children()

            def on_message(ws, message):
                line = message.strip()
                try:
                    ping = '"ping' in line
                    if len(line) > 0:
                        # TODO Need a better approach here
                        if ping:
                            self._ping_queue.put(line, block=False)
                            drops['ping_drop'] = 0
                        else:
                            self._queue.put(line, block=False)
                except Full:
                    log.info("Dropping request %s" % line)
                    drops['drop_count'] += 1
                    drop_max = Config.max_dropped_requests()
                    drop_type = 'overall'
                    drop_test = drops['drop_count']

                    if ping:
                        drops['ping_drop'] += 1
                        drop_type = 'ping'
                        drop_test = drops['ping_drop']
                        drop_max = Config.max_dropped_ping()

                    if drop_test > drop_max:
                        log.error('Max of [%s] dropped [%s] requests exceeded',
                                  drop_max, drop_type)
                        ws.close()

                if not _should_run(ppid):
                    log.info("Parent process has died or stamp changed,"
                             " exiting")
                    ws.close()

            def on_error(ws, error):
                raise Exception('Received websocket error: [%s]', error)

            def on_close(ws):
                log.info('Websocket connection closed.')

            def on_open(ws):
                log.info('Websocket connection opened')

            websocket.setdefaulttimeout(Config.event_read_timeout())
            ws = websocket.WebSocketApp(subscribe_url,
                                        header=headers,
                                        on_message=on_message,
                                        on_error=on_error,
                                        on_close=on_close,
                                        on_open=on_open)
            ws.run_forever()

        finally:
            for child in self._children:
                if hasattr(child, "terminate"):
                    try:
                        child.terminate()
                    except:
                        pass

        sys.exit(0)
