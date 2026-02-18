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

"""Managed ROS 2 launch sessions for reliable startup, monitoring, and shutdown."""

import contextlib
import threading

import launch
import launch.actions
import launch.event_handlers
import launch.events

from launch_testing.io_handler import ActiveIoHandler
from launch_testing.proc_info_handler import ActiveProcInfoHandler
from launch_testing.tools.process import ProcessProxy


class LaunchSession:
    """
    A managed launch session that provides reliable process lifecycle control.

    Composes existing ``launch`` and ``launch_testing`` APIs to provide:
    - Thread-safe process startup/shutdown monitoring
    - Output capture and pattern matching
    - Clean shutdown via LaunchService's SIGINT/SIGTERM/SIGKILL escalation

    Two usage modes:

    **Standalone mode** — owns the LaunchService, blocks on ``run()``:

    .. code-block:: python

        session = LaunchSession(my_launch_description)
        exit_code = session.run(on_ready=my_callback)

    **External service mode** — borrows an existing LaunchService:

    .. code-block:: python

        with LaunchSession.from_service(launch_service, my_ld) as session:
            session.wait_for_startup('my_node')
            # interact with the system...
    """

    def __init__(self, launch_description, *, noninteractive=True, debug=False):
        """
        Create a managed launch session.

        :param launch_description: The LaunchDescription to manage.
        :param noninteractive: If True (default), disable interactive features.
        :param debug: If True, enable debug output in the LaunchService.
        """
        self._launch_service = launch.LaunchService(
            noninteractive=noninteractive, debug=debug
        )
        self._proc_info = ActiveProcInfoHandler()
        self._proc_output = ActiveIoHandler()
        self._owns_service = True

        self._callback_error = None
        self._has_run = False

        self._wrapped_ld = self._wrap_launch_description(launch_description)

    @classmethod
    def _create_borrowed(cls, launch_service):
        """Create a session that borrows an existing LaunchService."""
        session = cls.__new__(cls)
        session._launch_service = launch_service
        session._proc_info = ActiveProcInfoHandler()
        session._proc_output = ActiveIoHandler()
        session._owns_service = False
        session._callback_error = None
        session._has_run = False
        session._wrapped_ld = None
        return session

    def _wrap_launch_description(self, launch_description):
        """
        Wrap a launch description with process tracking event handlers.

        This is the 4-handler pattern from launch_testing's _RunnerWorker.run().
        """
        return launch.LaunchDescription([
            launch.actions.RegisterEventHandler(
                launch.event_handlers.OnProcessStart(
                    on_start=lambda info, unused: self._proc_info.append(info)
                )
            ),
            launch.actions.RegisterEventHandler(
                launch.event_handlers.OnProcessStart(
                    on_start=lambda info, unused: self._proc_output.track(
                        info.process_name
                    )
                )
            ),
            launch.actions.RegisterEventHandler(
                launch.event_handlers.OnProcessExit(
                    on_exit=lambda info, unused: self._proc_info.append(info)
                )
            ),
            launch.actions.RegisterEventHandler(
                launch.event_handlers.OnProcessIO(
                    on_stdout=self._proc_output.append,
                    on_stderr=self._proc_output.append,
                )
            ),
            launch.actions.IncludeLaunchDescription(
                launch.LaunchDescriptionSource(
                    launch_description=launch_description
                )
            ),
        ])

    def run(self, on_ready=None, *, shutdown_when_idle=True):
        """
        Run the launch session, blocking until completion.

        Must be called from the main thread (LaunchService constraint).

        :param on_ready: Optional callback receiving this session. Called on a
            daemon thread immediately after the launch service starts processing.
            The callback should call ``shutdown()`` when done (a ``finally`` block
            ensures shutdown if the callback raises).
        :param shutdown_when_idle: If True (default), the launch service shuts
            down when all processes have exited.
        :returns: The launch service exit code.
        """
        if not self._owns_service:
            raise RuntimeError(
                'Cannot call run() on a session created with from_service(). '
                'The external LaunchService owns the event loop.'
            )

        if self._has_run:
            raise RuntimeError(
                'run() has already been called on this session. '
                'Create a new LaunchSession to run again.'
            )
        self._has_run = True

        self._launch_service.include_launch_description(self._wrapped_ld)

        if on_ready is not None:
            thread = threading.Thread(
                target=self._run_callback, args=(on_ready,), daemon=True
            )
            thread.start()

        exit_code = self._launch_service.run(
            shutdown_when_idle=shutdown_when_idle
        )

        if self._callback_error is not None:
            raise self._callback_error

        return exit_code

    def _run_callback(self, on_ready):
        """Run the on_ready callback, ensuring shutdown on completion."""
        try:
            on_ready(self)
        except Exception as e:
            self._callback_error = e
        finally:
            self.shutdown()

    def shutdown(self):
        """
        Shut down the launch session.

        Thread-safe. Triggers LaunchService's existing SIGINT → SIGTERM → SIGKILL
        escalation for all managed processes. Idempotent.
        """
        self._launch_service.shutdown()

    def wait_for_startup(self, process, *, timeout=10):
        """
        Block until a process starts.

        :param process: Process name or ExecuteProcess action.
        :param timeout: Seconds to wait before raising AssertionError.
        :raises AssertionError: If the process doesn't start within timeout.
        """
        self._proc_info.assertWaitForStartup(process, timeout=timeout)

    def wait_for_shutdown(self, process, *, timeout=10):
        """
        Block until a process exits.

        :param process: Process name or ExecuteProcess action.
        :param timeout: Seconds to wait before raising AssertionError.
        :raises AssertionError: If the process doesn't exit within timeout.
        """
        self._proc_info.assertWaitForShutdown(process, timeout=timeout)

    def wait_for_output(self, expected, *, process=None, timeout=10,
                        stream='stderr'):
        """
        Block until expected output appears.

        :param expected: Text to search for in process output.
        :param process: Process name to filter by, or None for all processes.
        :param timeout: Seconds to wait before raising AssertionError.
        :param stream: Output stream to search ('stderr' or 'stdout').
        :raises AssertionError: If the output doesn't appear within timeout.
        """
        self._proc_output.assertWaitFor(
            expected, process=process, timeout=timeout, stream=stream
        )

    def get_proxy(self, process_action, **kwargs):
        """
        Get a ProcessProxy for fine-grained process control.

        :param process_action: An ExecuteProcess action to proxy.
        :param kwargs: Additional arguments forwarded to ProcessProxy.
        :returns: A ProcessProxy instance.
        """
        return ProcessProxy(
            process_action, self._proc_info, self._proc_output, **kwargs
        )

    @property
    def proc_info(self):
        """Get the ActiveProcInfoHandler tracking process lifecycle events."""
        return self._proc_info

    @property
    def proc_output(self):
        """Get the ActiveIoHandler capturing process output."""
        return self._proc_output

    @property
    def launch_service(self):
        """Get the underlying LaunchService."""
        return self._launch_service

    @classmethod
    @contextlib.contextmanager
    def from_service(cls, launch_service, launch_description):
        """
        Use within an existing LaunchService context.

        Creates a session that borrows the given LaunchService (does not create
        a new one). The launch description is injected via ``emit_event()`` and
        the session is yielded for interaction.

        On context exit, calls ``shutdown()`` if processes are still running.

        :param launch_service: A LaunchService instance (caller is responsible
            for running it, typically on another thread).
        :param launch_description: The LaunchDescription to manage.
        :yields: A LaunchSession instance.
        """
        session = cls._create_borrowed(launch_service)
        wrapped_ld = session._wrap_launch_description(launch_description)

        launch_service.emit_event(
            launch.events.IncludeLaunchDescription(
                launch_description=wrapped_ld
            )
        )

        try:
            yield session
        finally:
            process_names = session._proc_info.process_names()
            if process_names:
                session.shutdown()
