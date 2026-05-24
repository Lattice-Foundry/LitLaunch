# Diagnostics Page Generator

LitLaunch can generate a small Streamlit-native diagnostics/support page for
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

## What The Generated Page Includes

The generated page uses native Streamlit components only. It collects
diagnostics with LitLaunch's existing diagnostics APIs and renders:

- runtime summary counts and LitLaunch version
- app/profile/project metadata
- runtime governance posture
- runtime exposure posture
- transport security posture
- platform, browser, target, and profile diagnostic sections
- in-memory downloads for HTML diagnostics, JSON diagnostics, and support bundle
- optional write buttons for `.litlaunch/reports/` artifacts
- optional recent runtime event log lines when `event_log_path` is configured

Artifacts are not written automatically on page render. The generated page only
writes files when a user clicks a write button.

This feature is not telemetry, a hosted dashboard, or a Streamlit framework.
LitLaunch only writes starter code; the host application owns the page.

## Runtime Event Trail

If your app uses LitLaunch's `RuntimeEvent` sink to write a product log, pass
the log path when generating the page:

```python
create_diagnostics_page(
    output_path="ui/litlaunch_diagnostics.py",
    app_name="RoleThread Lite",
    profile_name="rolethread-webapp",
    event_log_path=".litlaunch/runtime-events.log",
)
```

The generated page reads recent lines from that file if it exists. LitLaunch
does not create a logging framework, rotate files, or send telemetry.

## File Safety

The generator creates parent directories as needed and refuses to replace an
existing file unless `overwrite=True` is provided. Relative output paths are
resolved from `project_root` when supplied, otherwise from the current working
directory.
