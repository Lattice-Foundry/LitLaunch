# Diagnostics Page Generator

LitLaunch can generate a small Streamlit-native diagnostics page skeleton for
host applications. The generated file belongs to the app after it is written:
you decide where to mount it, how to style it, and whether to customize or
replace it.

LitLaunch itself does not depend on Streamlit for this feature. The generated
page imports Streamlit inside its render function so generation works even in
environments where Streamlit is not installed.

## Generate A Page

```python
from litlaunch import create_diagnostics_page

create_diagnostics_page(
    output_path="ui/litlaunch_diagnostics.py",
    app_name="RoleThread Lite",
    profile_name="rolethread-webapp",
)
```

Or use the builder API when you want to set options explicitly:

```python
from litlaunch import DiagnosticsPageBuilder

DiagnosticsPageBuilder(
    output_path="ui/litlaunch_diagnostics.py",
    function_name="render_litlaunch_diagnostics",
    page_title="Runtime Diagnostics",
    app_name="RoleThread Lite",
    profile_name="rolethread-webapp",
    overwrite=False,
).write()
```

Then mount the generated function wherever it fits your app:

```python
from ui.litlaunch_diagnostics import render_litlaunch_diagnostics

render_litlaunch_diagnostics()
```

## Current Scope

The first generator pass writes a valid, readable Streamlit page skeleton. Full
diagnostics sections, report buttons, and optional event-trail rendering are
planned for later generator passes.

This feature is not telemetry, a hosted dashboard, or a Streamlit framework.
LitLaunch only writes starter code; the host application owns the page.

## File Safety

The generator creates parent directories as needed and refuses to replace an
existing file unless `overwrite=True` is provided. Relative output paths are
resolved from `project_root` when supplied, otherwise from the current working
directory.
