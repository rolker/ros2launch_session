# ros2launch_session

Managed ROS 2 launch sessions for reliable startup, monitoring, and shutdown.

Composes existing `launch` and `launch_testing` APIs to provide:

- Thread-safe process startup/shutdown monitoring
- Output capture and pattern matching
- Clean shutdown via LaunchService's SIGINT/SIGTERM/SIGKILL escalation

## Usage

### Standalone mode

Owns the LaunchService and blocks on `run()`:

```python
import launch
import launch.actions
from ros2launch_session import LaunchSession

ld = launch.LaunchDescription([
    launch.actions.ExecuteProcess(
        cmd=['my_node'],
        output='both',
    ),
])

session = LaunchSession(ld)

def on_ready(s):
    s.wait_for_output('Ready', timeout=10, stream='stderr')
    # interact with the system...
    s.shutdown()

exit_code = session.run(on_ready=on_ready)
```

### External service mode

Borrows an existing LaunchService (e.g., from a test harness):

```python
with LaunchSession.from_service(launch_service, ld) as session:
    session.wait_for_startup('my_node')
    # interact with the system...
```

## API

- `LaunchSession(launch_description, *, noninteractive=True, debug=False)` — create a session
- `run(on_ready=None, *, shutdown_when_idle=True)` — run the session, blocking until completion
- `shutdown()` — trigger clean shutdown
- `wait_for_startup(process, *, timeout=10)` — block until a process starts
- `wait_for_shutdown(process, *, timeout=10)` — block until a process exits
- `wait_for_output(expected, *, process=None, timeout=10, stream='stderr')` — block until output appears
- `get_proxy(process_action, **kwargs)` — get a `ProcessProxy` for fine-grained control
- `LaunchSession.from_service(launch_service, launch_description)` — context manager for external service mode

## License

Apache-2.0
