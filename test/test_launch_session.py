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

import threading

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
            cmd=['sleep', '60'],
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


def test_wait_for_shutdown():
    """Verify wait_for_shutdown() returns after a short-lived process exits."""
    ld = launch.LaunchDescription([
        launch.actions.ExecuteProcess(
            cmd=['echo', 'done'],
            output='both',
        ),
    ])

    session = LaunchSession(ld)

    def on_ready(s):
        s.wait_for_shutdown('echo', timeout=10)

    exit_code = session.run(on_ready=on_ready)
    assert exit_code == 0


def test_from_service_with_running_service():
    """Verify from_service() works with a LaunchService running on the main thread."""
    ls = launch.LaunchService(noninteractive=True)

    # Include an empty launch description so the service has something to start with
    ls.include_launch_description(launch.LaunchDescription([]))

    errors = []

    def worker():
        try:
            ld = launch.LaunchDescription([
                launch.actions.ExecuteProcess(
                    cmd=['echo', 'from_service test'],
                    output='both',
                ),
            ])

            with LaunchSession.from_service(ls, ld) as session:
                session.wait_for_output(
                    'from_service test', timeout=10, stream='stdout'
                )
                session.wait_for_shutdown('echo', timeout=10)
        except Exception as e:
            errors.append(e)
        finally:
            ls.shutdown()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    # run() must be called from the main thread
    ls.run(shutdown_when_idle=False)
    thread.join(timeout=5)

    if errors:
        raise errors[0]


def test_run_twice_raises():
    """Verify that calling run() a second time raises RuntimeError."""
    ld = launch.LaunchDescription([
        launch.actions.ExecuteProcess(
            cmd=['echo', 'once'],
            output='both',
        ),
    ])

    session = LaunchSession(ld)
    session.run()

    with pytest.raises(RuntimeError, match='already been called'):
        session.run()


def test_callback_error_propagation():
    """Verify that exceptions from on_ready callbacks are re-raised by run()."""
    ld = launch.LaunchDescription([
        launch.actions.ExecuteProcess(
            cmd=['sleep', '10'],
        ),
    ])

    session = LaunchSession(ld)

    def on_ready(s):
        s.wait_for_startup('sleep', timeout=5)
        raise ValueError('test error from callback')

    with pytest.raises(ValueError, match='test error from callback'):
        session.run(on_ready=on_ready)
