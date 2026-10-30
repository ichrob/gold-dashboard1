"""Small-memory ONNX sessions for the isolated, network-disabled handset child."""
def offline_engine():
    # RapidOCR 1.4.4 exposes no graph-optimization option. Adapt its pinned
    # session-options factory only while constructing this child-local engine.
    # Basic optimizations avoid extra fused/prepacked weights; image inputs,
    # model weights, confidence thresholds and evidence rules remain unchanged.
    import onnxruntime
    from rapidocr_onnxruntime.utils import OrtInferSession
    from video_ocr import offline_engine as create
    descriptor=OrtInferSession.__dict__['_init_sess_opts']
    original=OrtInferSession._init_sess_opts
    def options(config):
        value=original(config)
        value.graph_optimization_level=onnxruntime.GraphOptimizationLevel.ORT_ENABLE_BASIC
        value.enable_mem_pattern=False
        return value
    OrtInferSession._init_sess_opts=staticmethod(options)
    try:return create()
    finally:OrtInferSession._init_sess_opts=descriptor
