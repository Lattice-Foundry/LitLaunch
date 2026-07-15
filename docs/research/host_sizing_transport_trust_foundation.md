# LL-HS1 Authenticated Host-Sizing Transport and Trust Foundation

- Date: 2026-07-14
- LitLaunch reference: 1.0.10
- Design references: `litbridge_host_sizing_consumption_recon.md` and
  `host_sizing_geometry_authority_spike.md`
- Scope: private transport foundation only

## Verdict

**TRANSPORT FOUNDATION PROVEN WITH LIMITATIONS**

LitLaunch can create a dedicated per-launch loopback endpoint that authenticates,
validates, sequences, and safely retains host-sizing reports. The endpoint has an
exact browser-origin policy, a separate capability token and launch ID, strict
protocol-v1 parsing, one-source authority, monotonic sequence handling, bounded
retention, request limits, credential redaction, and deterministic shutdown.

Real cross-origin browser requests succeeded in both Edge and Chrome without browser
security bypass flags. The accepted report was retained once with the expected source
and sequence.

The implementation remains private and inactive in normal LitLaunch launches. It does
not expose a CLI, profile, or supported Python setting, does not inject credentials
into a backend environment, and does not connect an accepted report to geometry or
window mutation. Production activation and browser-process authority remain later
work.

## Boundary

LL-HS1 adds a report-only control channel. It accepts observations but never acts on
them.

The transport module has no dependency on:

- `WindowsGeometryBackend`
- `SetWindowPos`
- `WindowSizer`
- `_host_sizing_geometry`
- browser discovery or window-monitoring code

No accepted, rejected, stale, or conflicting report can reach a native mutation seam.
This separation is covered by source-boundary tests in addition to the module design.

## Existing patterns reviewed

The shutdown channel provided several safe implementation patterns:

- cryptographically generated per-launch capability tokens
- literal loopback binding
- a short-lived threaded HTTP endpoint
- custom token headers rather than query-string credentials
- renderer redaction registration
- idempotent lifecycle cleanup
- backend environment handoff values

Host sizing remains a separate protocol, endpoint, token, and lifecycle object.
Shutdown is an action channel whose valid request triggers cleanup. Host sizing is an
observation channel whose valid request can only update a bounded in-memory snapshot.
The two channels do not share handlers or request semantics.

`RuntimeSession` already owns idempotent cleanup callbacks. A future activation path
can register `HostSizingChannel.close` there without changing session shutdown
semantics. LL-HS1 proves that callback path but does not start a channel from the
production launcher.

## Private protocol

The protocol accepts an exact JSON object with these fields:

```json
{
  "protocol": 1,
  "launch_id": "opaque-per-launch-id",
  "source_id": "primary-surface",
  "sequence": 7,
  "device_pixel_ratio": 1.0,
  "content": {
    "height": 742,
    "width": 1180
  },
  "host_viewport": {
    "height": 812,
    "width": 1280
  },
  "desired_host_viewport": {
    "height": 790
  }
}
```

Protocol rules:

- `protocol` must be integer `1`.
- `launch_id` must match the channel's per-launch ID.
- `source_id` is a bounded identifier and the first accepted source becomes the sole
  authority for the channel lifetime.
- `sequence` is a positive integer no greater than `2^63 - 1` and must increase
  strictly.
- `device_pixel_ratio` is required, finite, and bounded from 0.5 through 8.0.
- Each dimension object requires `height`; `width` is optional.
- Dimensions must be finite, positive, and no greater than 16,384 CSS pixels.
- Unknown fields, missing fields, duplicate JSON keys, non-finite constants,
  non-UTF-8 input, and non-object roots are rejected.
- Request bodies are limited to 4 KiB.

The endpoint returns `202 Accepted` only after all trust, schema, authority, sequence,
and rate checks pass.

## Authentication and origin policy

Each channel receives an independent random capability token and launch ID. The token
is sent in `X-LitLaunch-Host-Sizing-Token`, never in the endpoint URL. Authentication
and launch-ID checks use constant-time comparison.

The server binds only to literal `127.0.0.1` on a dedicated ephemeral port. Channel
creation rejects nonliteral bind hosts. The allowed browser origin must:

- use `http` or `https`
- resolve to loopback
- contain an explicit port
- contain no credentials, path, query, or fragment

Requests require an exact `Origin` match. CORS preflight permits only `POST`,
`Content-Type`, and the capability-token header. Private Network Access preflight is
acknowledged when a browser requests it. CORS response headers are never granted to a
different or missing origin.

Origin checks supplement the capability token; they are not treated as
authentication.

## Retention and sequencing

The in-memory store retains only the latest accepted report. It does not retain raw
request bodies, malformed payloads, credentials, or a report history.

The first accepted `source_id` owns report authority for the channel. Reports from a
second source fail closed. Duplicate and older sequences are rejected. Concurrent
requests are serialized under a lock, so the final snapshot remains monotonic even
when request completion order differs.

Accepted traffic is bounded to 60 reports per second and 1,024 accepted reports per
channel. Rejection counts retain only reason categories. They do not retain payloads,
headers, tokens, origins, or request text.

## Lifecycle and failure handling

Channel startup validates trust configuration before binding. A bind failure closes
the report store and leaves no endpoint thread. A later startup failure closes the
store and server before propagating the error.

Shutdown is idempotent. It marks the store closed before stopping the HTTP server, so
no accepted report can race past lifecycle closure. The final credential-free
snapshot remains available after close. `RuntimeSession` cleanup-callback coverage
proves that normal session cleanup closes the channel.

The HTTP server disables request logging. Endpoint configuration hides the token from
`repr`, and the token is registered with the existing console renderer before the
channel is returned. Environment previews use the existing sensitive-key redaction
path. The endpoint URL is token-free.

## Browser evidence

A temporary loopback page sent a real `fetch` request to a separate host-sizing port.
The probe used the exact origin and capability header, exercised the browser's normal
CORS preflight, and did not use CORS, web-security, or Private Network Access bypass
flags.

Results:

- Microsoft Edge: `202 accepted`; one report retained at sequence 1.
- Google Chrome: `202 accepted`; one report retained at sequence 1.

The browser profile, page server, host-sizing channel, and temporary files were
closed after each probe.

## Validation evidence

Focused transport validation covers:

- literal loopback and exact-origin configuration
- partial-startup failure cleanup
- token and launch-ID authentication
- CORS and Private Network Access preflight
- content type, content length, and body limits
- strict schema and JSON parsing
- source authority and monotonic sequencing
- concurrent report ordering
- rate and total acceptance limits
- bounded, credential-free snapshots
- renderer and environment-preview redaction
- idempotent close and `RuntimeSession` cleanup
- absence from public exports
- absence of geometry and native mutation dependencies

Final results:

- `python -m pytest tests/test_host_sizing_transport.py -q`: 40 passed
- `python -m pytest`: 815 passed, including the real Streamlit smoke test
- `python -m ruff check .`: passed
- `python -m ruff format --check .`: passed
- `python -m mypy src/litlaunch`: passed for 76 source files
- `python scripts/check_release.py`: passed; wheel and source distribution built,
  checked, installed, and reported version 1.0.10

## Limitations and next gate

- No public host-sizing configuration or supported API exists.
- Normal LitLaunch launches do not start this endpoint.
- The private environment handoff shape is defined but not injected into Streamlit.
- No application adapter has been implemented or tested.
- HTTPS loopback origins were validated structurally but not exercised with a live
  certificate.
- The channel's 1,024-report lifetime limit is suitable for bounded initial-fit work;
  any later continuous policy must define a different lifecycle deliberately.
- LL-HS0's browser-process authority limitation remains. Transport success does not
  authorize window mutation.

The next pass may build an internal sizing-policy state machine against retained
snapshots and fake mutation collaborators. Production window mutation must remain
disconnected until exact launch-associated browser authority is available on the
selected launch path.

**TRANSPORT FOUNDATION PROVEN WITH LIMITATIONS**
