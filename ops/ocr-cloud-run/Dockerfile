FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libseccomp2 libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY ops/ocr-cloud-run/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY handset_list_worker.py handset_ocr_engine.py video_ocr.py memory_watch.py ocr_sandbox.py ocr_workload_priority.py /app/
COPY ops/ocr-cloud-run/server.py ops/ocr-cloud-run/smoke.py /app/ops/ocr-cloud-run/
USER 65532
EXPOSE 8080
CMD ["python", "ops/ocr-cloud-run/server.py"]
