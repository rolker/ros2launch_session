# Copyright 2025 University of New Hampshire, Center for Coastal and Ocean Mapping
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Functional tests for LaunchSession."""

import launch
import launch.actions
import pytest

from ros2launch_session import LaunchSession


def test_echo_and_shutdown():
    """Verify that a simple echo command runs, output is captured, and exits cleanly."""
    ld = launch.LaunchDescription([
        launch.actions.ExecuteProcess(
            cmd=['echo', 'hello launch session'],
            output='both',
        ),
    ])

    session = LaunchSession(ld)

    def on_ready(s):
        s.wait_for_output('hello launch session', timeout=10, stream='stdout')

    exit_code = session.run(on_ready=on_ready)
    assert exit_code == 0


def test_shutdown_long_running_process():
    """Verify that shutdown() terminates a long-running process cleanly."""
    ld = launch.LaunchDescription([
        launch.actions.ExecuteProcess(
            cmd=['sleep', '300'],
        ),
    ])

    session = LaunchSession(ld)

    def on_ready(s):
        s.wait_for_startup('sleep', timeout=10)
        s.shutdown()

    exit_code = session.run(on_ready=on_ready)
    # Exit code is non-zero because sleep was killed
    assert exit_code is not None


def test_run_not_allowed_on_borrowed_service():
    """Verify that run() raises on a borrowed-service session."""
    ls = launch.LaunchService(noninteractive=True)
    ld = launch.LaunchDescription([])

    with pytest.raises(RuntimeError, match='Cannot call run'):
        with LaunchSession.from_service(ls, ld) as session:
            session.run()
