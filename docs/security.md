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

## Runtime Exposure Diagnostics

`litlaunch inspect` and `litlaunch report` include a runtime exposure posture
section. It reports:

- configured host
- exposure scope, such as `loopback`, `wildcard_bind`, `local_network`, or
  `public_or_unknown`
- active trust mode
- whether network exposure was explicitly acknowledged
- whether the current trust mode allows or blocks the configured binding
- practical reminders about shutdown hooks, diagnostics privacy, plaintext
  profile environment values, and browser ownership boundaries

This is operational visibility, not a subjective security score. A warning or
error means the runtime configuration deserves attention; it does not mean
LitLaunch has secured or failed to secure the Streamlit application.

## Transport Security Diagnostics

`litlaunch inspect` and `litlaunch report` also include a transport security
section. LitLaunch detects Streamlit-native TLS settings when they are provided
through supported Streamlit flag/profile paths:

```toml
[profiles.internal-dashboard.streamlit_flags]
"server.sslCertFile" = "cert.pem"
"server.sslKeyFile" = "key.pem"
```

When both `server.sslCertFile` and `server.sslKeyFile` are present, LitLaunch
reports Streamlit-native TLS as configured. When only one is present, LitLaunch
reports incomplete TLS configuration. Certificate and key paths are summarized
rather than printed into diagnostics.

For non-loopback hosts without TLS settings, diagnostics warn that traffic
appears to be network-visible plaintext HTTP. That warning is intentionally
operational: LitLaunch does not terminate TLS, generate certificates, manage
certificates, add authentication, or create a reverse proxy.

Transport guidance:

- local loopback development does not usually need TLS
- internal-network apps should use approved infrastructure controls
- Streamlit-native TLS can encrypt transport, but it does not authenticate users
  or make the Streamlit app secure by itself
- corporate/internal deployments often belong behind an approved reverse proxy,
  VPN, gateway, or other platform-owned boundary

## Internal Network Recommendations

For internal dashboards and analyst tools:

- keep loopback binding for local-only tools
- expose only on trusted networks with known firewall/routing boundaries
- put authentication, TLS, and access control outside LitLaunch when needed
- treat non-loopback HTTP as network-visible plaintext
- review generated HTML reports and support bundles before sharing
- avoid storing secrets in profile `extra_env`; those values are plaintext TOML

LitLaunch's goal is to make runtime behavior visible and controlled. It is not a
replacement for application security or network security.
