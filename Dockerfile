FROM ghcr.io/astral-sh/uv:0.13.1 AS uv

# First, bundle the dependencies into the task root.
FROM public.ecr.aws/lambda/python:3.12 AS builder

# Enable bytecode compilation, to improve cold-start performance.
ENV UV_COMPILE_BYTECODE=1

# Disable installer metadata, to create a deterministic layer.
ENV UV_NO_INSTALLER_METADATA=1

# Enable copy mode to support bind mount caching.
ENV UV_LINK_MODE=copy

# Bundle the dependencies into the Lambda task root via `uv pip install --target`.
#
# This keeps the layer cached across changes to application code, as long as uv.lock is unchanged.
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv export --frozen --no-dev --no-editable -o requirements.txt && \
    uv pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

FROM public.ecr.aws/lambda/python:3.12

# Copy the runtime dependencies from the builder stage.
COPY --from=builder ${LAMBDA_TASK_ROOT} ${LAMBDA_TASK_ROOT}

# Copy only the application package -- evals/, tests/, scripts/, docs/ are not
# needed by the running service.
COPY remember_this/ ${LAMBDA_TASK_ROOT}/remember_this/

# Lambda's own entry point convention: <module path>.<handler function name>.
CMD ["remember_this.bot.webhook.handler"]
