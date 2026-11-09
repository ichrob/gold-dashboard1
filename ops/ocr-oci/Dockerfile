FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
WORKDIR /app
ARG TARGETARCH
RUN test "$TARGETARCH" = "arm64"
RUN apt-get update && apt-get install -y --no-install-recommends libseccomp2 libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY ops/ocr-oci/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY handset_list_worker.py handset_ocr_engine.py video_ocr.py memory_watch.py ocr_sandbox.py ocr_workload_priority.py /app/
COPY ops/ocr-oci/server.py ops/ocr-oci/smoke.py /app/ops/ocr-oci/
USER 65532
EXPOSE 8443
CMD ["python", "ops/ocr-oci/server.py"]
