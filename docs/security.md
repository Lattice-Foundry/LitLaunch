# Security And Trust Boundaries

LitLaunch is a local runtime governance layer for Streamlit apps. It improves
operational safety around launch, shutdown, diagnostics, and generated project
assets, but it does not secure a Streamlit application by itself.

## What LitLaunch Does

- defaults to loopback host binding for local development
- starts Streamlit with explicit argument tuples rather than shell strings
- owns and stops only the backend process it starts
- provides tokened loopback graceful-shutdown hooks for app cleanup
- warns before launching with non-loopback host bindings
- redacts common sensitive values in diagnostics and avoids raw environment dumps
- writes project-local profiles and shortcuts with validation and overwrite checks

## What LitLaunch Does Not Do

- add authentication or authorization to Streamlit
- create a reverse proxy, TLS layer, VPN, firewall, or identity boundary
- make a network-exposed Streamlit app safe for untrusted users
- own, kill, or control browser processes
- guarantee that diagnostics redaction catches every possible secret format

## Network Exposure

The default host is `127.0.0.1`, which is loopback-only. Binding to a
non-loopback host such as `0.0.0.0`, `::`, a LAN IP, or an internal hostname may
make the app reachable from the local network or a broader network depending on
routing and firewall configuration.

LitLaunch requires explicit acknowledgement before launching with a
non-loopback host:

```powershell
litlaunch app.py --host 0.0.0.0 --allow-network-exposure
```

Profiles can also acknowledge intentional exposure:

```toml
[profiles.internal-dashboard]
app_path = "app.py"
host = "0.0.0.0"
allow_network_exposure = true
```

For automation environments, `LITLAUNCH_ALLOW_NETWORK_EXPOSURE=1` can provide
the same acknowledgement. Use that only where the deployment boundary is already
understood.

## Trust Modes

Trust modes declare the operational intent for a launch. They govern LitLaunch
runtime behavior and diagnostics; they do not add authentication, TLS, or
application security to Streamlit.

- `development`: default mode for local development. Loopback launches are
  smooth; non-loopback launches still require explicit exposure acknowledgement.
- `strict_local`: hard localhost-only mode. Non-loopback hosts are refused even
  when `--allow-network-exposure`, profile acknowledgement, or environment
  acknowledgement is present.
- `internal_network`: intended for deliberate LAN/internal deployment. Loopback
  launches work normally; non-loopback hosts require explicit exposure
  acknowledgement and still render the network-exposure warning.

CLI usage:

```powershell
litlaunch app.py --trust-mode strict_local
litlaunch app.py --host 0.0.0.0 --trust-mode internal_network --allow-network-exposure
```

Profile usage:

```toml
[profiles.internal-dashboard]
app_path = "app.py"
host = "0.0.0.0"
trust_mode = "internal_network"
allow_network_exposure = true
```

## Internal Network Recommendations

For internal dashboards and analyst tools:

- keep loopback binding for local-only tools
- expose only on trusted networks with known firewall/routing boundaries
- put authentication, TLS, and access control outside LitLaunch when needed
- review generated HTML reports and support bundles before sharing
- avoid storing secrets in profile `extra_env`; those values are plaintext TOML

LitLaunch's goal is to make runtime behavior visible and controlled. It is not a
replacement for application security or network security.
