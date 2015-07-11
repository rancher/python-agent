#pyagent

[![Build Status](http://drone.rancher.io/api/badge/github.com/rancherio/python-agent/status.svg?branch=master)](http://drone.rancher.io/github.com/rancherio/python-agent)

This agent runs on compute nodes in a Rancher cluster. It receives events from the Rancher server, acts upon them, and returns response events.

### Deployment notes
This agent is typically deployed inside a container on Rancher compute nodes. See [the Rancher project](http://github.com/rancherio/rancher) for details.

### Setup and Development notes
#### On Mac OS X
Steps to get the tests running and passing:

1. Have boot2docker up and running
1. Create virtual environment and install python dependencies:

  ```
  $ mkdir venv && virtualenv venv && . venv/bin/activate
  $ pip install -r requirements.txt
  $ pip install -r test-requirements.txt
  ```
1. Run the tests:

  ```
  mkdir $HOME/cattle-home
  $ CATTLE_DOCKER_USE_BOOT2DOCKER=true CATTLE_HOME=$HOME/cattle-home py.test tests
  ```
  Or you can do the equivalent in PyCharm. An explanation of those environment variables:
  * ```CATTLE_DOCKER_USE_BOOT2DOCKER=true``` tells the docker client to use the connection settings derived from ```boot2docker shellinit```. You need this because boot2docker has TLS enabled by default.
  * ```CATTLE_HOME``` is needed for some temporary files that are written (locks, specifically)

## Contact
For bugs, questions, comments, corrections, suggestions, etc., open an issue in
 [rancher/rancher](//github.com/rancher/rancher/issues) with a title starting with `[Python-Agent] `.

Or just [click here](//github.com/rancher/rancher/issues/new?title=%5BPython-Agent%5D%20) to create a new issue.


# License
Copyright (c) 2014-2015 [Rancher Labs, Inc.](http://rancher.com)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

[http://www.apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0)

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

