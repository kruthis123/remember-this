# Step 10 — Deploy (Dockerfile, AWS Lambda, GitHub Actions on tag)

Design references: ADR-006 (webhook on a scale-to-zero host, Neon Postgres — the compute/datastore decision
this step builds for, amended below) and ADR-010 (prompts in git, deploy triggered by a git tag rather than
every push to main). Reread ADR-010's "Options considered → Deployment" section specifically, since the
trigger shape (`v*` tag, not push-to-main) is a deliberate choice, not a default.

**Deviation from the original plan, recorded in ADR-006's amendment section:** this step originally targeted
Cloud Run. GCP requires a billing account linked to the project even for free-tier usage, which was declined.
AWS App Runner — the direct Cloud Run equivalent — stopped accepting new customers as of April 30, 2026, so
it wasn't available as a substitute either. AWS Lambda, behind a Lambda Function URL, is what this project
actually runs on. Read the ADR-006 amendment before this doc if you want the full reasoning; this doc
describes what was actually built.

Everything app-side is already done, including the Lambda-specific handler rewrite in
`remember_this/bot/webhook.py` (see ADR-006's amendment for why that rewrite was necessary and not just a
hosting swap). This step containerizes it, gets it onto Lambda by hand to prove the setup, then should
automate that same path behind a tag push. **The manual path (Parts 1–7) is done and verified end-to-end
against a real Telegram client. The GitHub Actions automation (Part 8) is still open.**

---

## Files written

| File | Purpose |
|---|---|
| `Dockerfile` | Builds a Lambda container image from `public.ecr.aws/lambda/python:3.12`, using `uv` to install dependencies. |
| `.dockerignore` | Keeps `.venv`, `.env`, caches, and eval/test/doc content out of the build context. |
| `remember_this/bot/webhook.py` | Rewritten from a FastAPI app to a Lambda handler function (see ADR-006 amendment). |
| `scripts/register_webhook.py` | Updated to take a single Function URL argument instead of a base URL + path token (Lambda Function URLs have no router to attach a path segment to). |
| `.github/workflows/deploy.yml` | **Not yet written.** On a `v*` tag push: build image, push to ECR, update the Lambda function. |

---

## Part 0 — Concepts

### Why a container, and why this specific base image

Lambda runs code two ways: a zip upload (250MB limit, must match Lambda's runtime exactly) or a container
image (up to 10GB, pulled from ECR). This project's dependencies — `asyncpg`'s compiled C extension,
`pydantic-ai`, `langfuse` — are too large and too platform-specific to risk the zip path, so this uses a
container image built from AWS's own Lambda base image (`public.ecr.aws/lambda/python:3.12`), not a generic
`python:3.12-slim`. The Lambda base image bakes in the Lambda Runtime Interface Client, which is what lets
Lambda invoke `CMD`'s target as a handler function rather than running it as a long-lived server process.

### `uv` in a Lambda image is `uv pip install --target`, not `uv sync`

A normal `uv` Docker pattern creates a `.venv` and activates it. Lambda's container contract expects
dependencies to be importable directly from `${LAMBDA_TASK_ROOT}` (`/var/task`), with no venv activation
step in between. `uv`'s own AWS Lambda guide
(https://docs.astral.sh/uv/guides/integration/aws-lambda/) uses `uv export` to produce a `requirements.txt`
from `uv.lock`, then `uv pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"` — installing
packages flat into the directory Lambda will actually import from, inside a multi-stage build so the `uv`
binary itself and build caches don't end up in the final image. This project's `Dockerfile` follows that
guide directly.

### Lambda does not run `uvicorn`, or any server

There is no `$PORT`, no listening socket, no FastAPI app in the running container at all. Lambda's runtime
invokes a single Python function — the "handler" — once per incoming event, with the event already parsed
out of whatever triggered it (a Function URL request, in this case). `CMD` in a Lambda image names that
function as `<module path>.<function name>`, e.g. `remember_this.bot.webhook.handler`, not a shell command
to execute.

### Lambda handlers are synchronous, and that has a real consequence here

Lambda does not support `async def` as a handler signature. This project's handler is a plain `def` that
drives its own `asyncio` event loop. The subtlety: `asyncpg.Pool` is bound to the event loop that created
it. If the handler created a fresh loop per invocation (e.g. via `asyncio.run()`, which closes the loop when
it returns), the connection pool would die after the first invocation on an otherwise-warm container, and
every call after that would fail against a closed loop. `webhook.py` instead creates one `asyncio.new_event_loop()`
at module scope and reuses it across warm invocations via `loop.run_until_complete(...)` per call — the same
spirit as the "initialize reusable resources outside the handler" guidance AWS gives for database
connections, just applied to the event loop itself since that's what the pool is actually bound to.

### Function URL vs. API Gateway

A Lambda Function URL is a dedicated HTTPS endpoint for one function, with no routing, request
transformation, or usage-plan machinery in front of it — closer to Cloud Run's own "just gives you a URL"
model than API Gateway is. Since this webhook is a single route with no sub-paths, a Function URL is the
right fit; API Gateway would add configuration for capabilities this project doesn't use.

### Auth on the Function URL: `NONE`, by design, not by oversight

A Function URL's `AuthType` is either `AWS_IAM` (caller must sign the request with AWS credentials — not
possible for Telegram, which can't do SigV4) or `NONE` (publicly reachable, no AWS-level gate at all). This
project uses `NONE`, same as it would have on Cloud Run: the real authentication is the
`X-Telegram-Bot-Api-Secret-Token` header check already inside `webhook.py`, matched against
`settings.telegram_webhook_secret`. The URL itself grants no protection — anyone who finds it can POST to
it — but the handler rejects anything without the right header before doing anything else. Separately from
`AuthType`, Lambda also requires the function's own resource-based policy to explicitly allow
`lambda:InvokeFunctionUrl` and (as of a change in late 2025) `lambda:InvokeFunction` with the
`lambda:InvokedViaFunctionUrl` condition — both must be added via `aws lambda add-permission`; `NONE` alone
is not sufficient and produces a `403 Forbidden` from AWS's own layer, not from the handler, if either is
missing.

### What ships vs. what's injected

The image ships code only. Every `SecretStr` field on `Settings` (`telegram_bot_token`,
`telegram_webhook_secret`, `llm_api_key`, `langfuse_public_key`, `langfuse_secret_key`, `database_url`,
`user_id_salt`) and every plain config value is read from `.env` locally — in the deployed function there is
no `.env` file in the image (excluded by `.dockerignore`), so they arrive as Lambda environment variables
set directly on the function. `pydantic-settings`'s `env_file=".env"` is harmless when the file is absent;
it falls through to real process environment variables.

---

## Part 1 — AWS setup (done)

What exists now, for reference:

- ECR repository `remember-this` in `ap-southeast-1`, holding the pushed image.
- IAM role `remember-this-lambda-role`, trust policy scoped to `lambda.amazonaws.com`, with only
  `AWSLambdaBasicExecutionRole` attached (CloudWatch Logs access) — the function talks to Neon, the
  university LLM endpoint, Langfuse, and Telegram, none of which are AWS services, so it needs no other AWS
  permissions.
- Lambda function `remember-this-bot`, `arm64` architecture (matches the build machine, and Graviton2 is
  typically cheaper), 512MB memory, 60s timeout.
- A Function URL with `AuthType=NONE`, plus the two resource-policy statements from Part 0's auth note.
- Environment variables set directly on the function (plain env vars, not Secret Manager/Secrets Manager —
  a real tradeoff worth naming if this gets written up: AWS Secrets Manager would give versioning and
  rotation and cost a small per-secret monthly fee and more setup; plain env vars were chosen here the same
  way plain Cloud Run env vars would have been, for the same reason — five users, free tier, simplicity over
  an audit story nobody's asking for yet).

None of the actual resource names/account ID need to be committed to this repo; they're recorded here only
as documentation of what was done.

---

## Part 2 — `Dockerfile` (done)

```dockerfile
FROM ghcr.io/astral-sh/uv:0.13.1 AS uv

FROM public.ecr.aws/lambda/python:3.12 AS builder
ENV UV_COMPILE_BYTECODE=1
ENV UV_NO_INSTALLER_METADATA=1
ENV UV_LINK_MODE=copy
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv export --frozen --no-dev --no-editable -o requirements.txt && \
    uv pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

FROM public.ecr.aws/lambda/python:3.12
COPY --from=builder ${LAMBDA_TASK_ROOT} ${LAMBDA_TASK_ROOT}
COPY remember_this/ ${LAMBDA_TASK_ROOT}/remember_this/
CMD ["remember_this.bot.webhook.handler"]
```

Verified locally with Lambda's own Runtime Interface Emulator (built into the base image, exposed on port
8080 inside the container): `docker run --rm -p 9100:8080 --env-file .env remember-this-lambda`, then POSTing
a hand-built event to `http://localhost:9100/2015-03-31/functions/function/invocations` — confirmed the
secret-token check, idempotency against the real Neon DB, and command routing all work inside the container
before anything touched AWS.

**Build flag note, learned the hard way:** `docker build` with modern BuildKit attaches a provenance/SBOM
attestation manifest by default, which Lambda's `create-function` rejects with "image manifest ... is not
supported." Build with `docker build --provenance=false --sbom=false ...` for images destined for Lambda.

---

## Part 3 — `.dockerignore` (done)

```
.venv
.env
.env.example
.git
__pycache__
**/__pycache__
*.pyc
.kiro
evals/
tests/
scripts/
docs/
*.md
.python-version
```

Same reasoning as the original plan: a broad `COPY . .` picking up `.env` would bake real secrets into an
image layer retrievable by anyone who can pull it. This project's `Dockerfile` copies `remember_this/`
explicitly rather than `COPY . .`, which is a second, independent guard against the same mistake.

---

## Part 4 — Secrets into Lambda (done)

Every no-default `Settings` field was set as a Lambda environment variable via
`aws lambda update-function-configuration --environment "Variables={...}"`. Two real mistakes made and
fixed during this step, worth recording so they don't repeat:

- `aws lambda update-function-configuration` **replaces** the entire `Variables` map, it does not merge. An
  update called with an accidentally empty variable set wiped every environment variable the function had,
  silently, with no warning. Always re-read the full current set and re-apply it in full, never patch in an
  assumed-correct partial set.
- Lambda's own image-format validation only runs at `create-function`/`update-function-code` time and gave a
  confusing "media type ... not supported" error that had nothing to do with the actual fix (Part 2's
  `--provenance=false` flag).

---

## Part 5 — Function URL and permissions (done)

```bash
aws lambda create-function-url-config --function-name remember-this-bot --auth-type NONE
aws lambda add-permission --function-name remember-this-bot \
  --statement-id FunctionURLAllowPublicAccess --action lambda:InvokeFunctionUrl \
  --principal "*" --function-url-auth-type NONE
aws lambda add-permission --function-name remember-this-bot \
  --statement-id UrlPolicyInvokeFunction --action lambda:InvokeFunction \
  --principal "*" --invoked-via-function-url
```

The second `add-permission` call is easy to miss — older guides and some AWS examples only show the first.
Without it, every request gets a `403 Forbidden` directly from AWS's authorizer layer, before the handler
ever runs, which looks identical from the outside to a webhook secret mismatch but has nothing to do with
the handler's own 401 response. If you see a bare `{"Message": "Forbidden. ..."}` body rather than this
project's own JSON error shape, it's this permission, not the handler.

---

## Part 6 — First real deploy (done)

Image built, tagged, and pushed to ECR; function created pointing at that image; both resource-policy
statements added; environment variables applied. Confirmed via `aws logs tail /aws/lambda/remember-this-bot`
that the container starts cleanly (Langfuse auth check succeeds) and that invocations complete normally —
checked logs directly rather than trusting a successful `create-function` call alone, since (per the
original plan's own pitfall list) a function can be created successfully and still fail at every actual
invocation.

---

## Part 7 — The deferred step-9 check, now for real (done)

With a real `TELEGRAM_BOT_TOKEN` (from BotFather) and `TELEGRAM_WEBHOOK_SECRET` set on the live function:

```bash
uv run python -m scripts.register_webhook https://<function-id>.lambda-url.<region>.on.aws/
```

Confirmed via `getWebhookInfo` that Telegram registered the URL with no pending/failed updates. Ran a full
real conversation from an actual Telegram client: `/help`, a multi-fact feed message (confirmed extraction
split it into separate atomic facts), a recall question, a genuine abstention (something never stored), a
second unrelated fact and its recall, a non-text message (confirmed the "I only understand text messages"
fallback), and a real `/forget` round trip — tapping the actual inline keyboard button, not a simulated
callback — followed by a re-ask confirming the deletion took effect. All 18 Lambda invocations across that
conversation completed normally with no errors, confirmed directly from CloudWatch Logs
(`aws logs tail /aws/lambda/remember-this-bot`).

---

## Part 8 — `.github/workflows/deploy.yml` (not yet done)

Still to write. Trigger, per ADR-010, unchanged by the Lambda swap:

```yaml
on:
  push:
    tags:
      - "v*"
```

Shape to build toward: authenticate to AWS via OIDC (GitHub's `aws-actions/configure-aws-credentials` with
a `role-to-assume`, no stored access key — AWS's equivalent of what Workload Identity Federation is on GCP,
same underlying idea of exchanging GitHub's own short-lived OIDC token for cloud credentials with nothing
long-lived sitting in GitHub secrets), then `docker build --provenance=false --sbom=false`, push to ECR, and
`aws lambda update-function-code --image-uri ...` to roll the function onto the new image. This needs its
own IAM role (distinct from `remember-this-lambda-role`, which is the function's *execution* role, not a
deploy-time role) trusted for GitHub's OIDC issuer, scoped to exactly `ecr:*` on the one repo and
`lambda:UpdateFunctionCode` on the one function — not broad account access.

As with the original Cloud Run plan, ADR-010 explicitly accepts that nothing in CI checks an eval run
happened before the tag; that gap is unchanged by this step and not something to close here.

---

## Pitfalls

- `update-function-configuration`'s `Variables` map is a full replace, not a merge — always re-apply the
  complete set, never a partial one.
- Modern `docker build`'s default provenance/SBOM attestation is rejected by Lambda's image validator —
  build with `--provenance=false --sbom=false` for any image destined for `create-function` or
  `update-function-code`.
- A Function URL with `AuthType=NONE` still needs **two** separate `add-permission` statements
  (`InvokeFunctionUrl` and, since late 2025, `InvokeFunction` with `--invoked-via-function-url`) — missing
  either produces a `403` from AWS itself, not from the application.
- Lambda does not support `async def` handlers; a handler that calls `asyncio.run()` per invocation will
  silently break `asyncpg`'s pool on the second invocation of a warm container, because the pool is bound
  to a now-closed loop. Keep one persistent loop at module scope instead.
- A green `create-function`/`update-function-code` call is not proof the service works — check CloudWatch
  Logs for the actual invocation, same caution the original Cloud-Run-era doc gave for Cloud Run's own logs.

## Done when

- [x] `docker build` succeeds locally and the image, run via Lambda's Runtime Interface Emulator, serves the
  webhook handler correctly on your machine.
- [x] The function is live on AWS with a working Function URL, confirmed via CloudWatch Logs that
  invocations complete without error.
- [x] `register_webhook.py` run against the real Function URL, confirmed via `getWebhookInfo`.
- [x] A real message from an actual Telegram client round-trips correctly: a multi-fact stored feed, a
  recalled answer, a genuine abstention, a non-text fallback, and a completed `/forget` with a real
  button tap.
- [ ] A `v*` tag push runs a GitHub Actions workflow to a green state with no manual intervention.
- [ ] Cold vs. warm latency noted deliberately (one data point exists: ~5.7s container init + Neon wake on
  a cold first call — a second, deliberate before/after-idle comparison is still owed).
- [ ] `USER_ID_SALT` replaced with a real random secret before treating this as more than a scratch
  deployment — it is currently still `placeholder` on the live function.
- You can state, in one sentence, why this project ended up on Lambda instead of the originally-planned
  Cloud Run, and why that required a code change rather than only a redeploy.
