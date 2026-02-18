# ros2launch_session

Managed ROS 2 launch sessions for reliable startup, monitoring, and shutdown.

## What this is (and isn't)

This is **not** a replacement for launch files. You still write
`_launch.py` files for your packages and use `ros2 launch` as usual.

`ros2launch_session` is a **programmatic wrapper** for when you need to
launch ROS 2 processes from Python code — integration tests, automation
scripts, or AI agents debugging a system — and need more control than
shelling out to `ros2 launch` gives you.

Problems it solves:

- **Zombie processes** — if your test crashes or an agent's session is
  interrupted, child processes get left running. `LaunchSession` guarantees
  cleanup through `launch`'s SIGINT → SIGTERM → SIGKILL escalation.
- **Shutdown ordering** — killing a launch file doesn't always clean up all
  its children. `LaunchSession` manages the full process tree.
- **Readiness detection** — instead of `time.sleep(5)` and hoping a node is
  up, you can `wait_for_startup()` or `wait_for_output('Ready')` and
  proceed as soon as the process is actually ready.

It builds on `launch` and `launch_testing` — no new process management,
just a simpler interface to the machinery that already exists.

## Usage

### Standalone mode

Create a session, pass a callback to run once the launch service is up:

```python
import launch
import launch.actions
from ros2launch_session import LaunchSession

ld = launch.LaunchDescription([
    launch.actions.ExecuteProcess(
        cmd=['ros2', 'run', 'demo_nodes_cpp', 'talker'],
        output='both',
    ),
])

session = LaunchSession(ld)

def on_ready(s):
    # Block until the node is actually publishing
    s.wait_for_output('Publishing', timeout=10, stream='stdout')
    # ... interact with the running system ...
    s.shutdown()

exit_code = session.run(on_ready=on_ready)
```

The `on_ready` callback runs on a background thread while `run()` blocks
the main thread (a `LaunchService` requirement). When the callback returns
or raises, the session shuts down automatically.

### External service mode

If you already have a `LaunchService` running (e.g., in a test harness),
you can inject a launch description into it without creating a new one:

```python
import threading

import launch
import launch.actions
from ros2launch_session import LaunchSession

# An existing LaunchService, running on the main thread
ls = launch.LaunchService(noninteractive=True)
ls.include_launch_description(launch.LaunchDescription([]))

ld = launch.LaunchDescription([
    launch.actions.ExecuteProcess(
        cmd=['ros2', 'run', 'demo_nodes_cpp', 'listener'],
        output='both',
    ),
])

# Use from_service() on a worker thread while ls.run() blocks the main thread
def worker():
    with LaunchSession.from_service(ls, ld) as session:
        session.wait_for_startup('listener')
        # ... interact ...
    ls.shutdown()

threading.Thread(target=worker, daemon=True).start()
ls.run(shutdown_when_idle=False)
```

On context exit, any processes still running are shut down automatically.

## API

| Method | Description |
|--------|-------------|
| `LaunchSession(ld, *, noninteractive=True, debug=False)` | Create a session that owns its own `LaunchService` |
| `run(on_ready=None, *, shutdown_when_idle=True)` | Run the session, blocking until completion |
| `shutdown()` | Trigger clean shutdown (thread-safe, idempotent) |
| `wait_for_startup(process, *, timeout=10)` | Block until a process starts |
| `wait_for_shutdown(process, *, timeout=10)` | Block until a process exits |
| `wait_for_output(expected, *, process=None, timeout=10, stream='stderr')` | Block until output appears |
| `get_proxy(process_action, **kwargs)` | Get a `ProcessProxy` for fine-grained control |
| `LaunchSession.from_service(ls, ld)` | Context manager — borrow an existing `LaunchService` |

The `process` argument in wait methods accepts either a process name (string)
or an `ExecuteProcess` action object.

## License

Apache-2.0
