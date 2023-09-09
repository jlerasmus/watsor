import argparse
import os

try:
    import tensorrt as trt
except ImportError as e:
    if __name__ != '__main__':
        raise e
    else:
        print('TensorRT is not installed, skipping.')
        exit()

TRT_LOGGER = trt.Logger(trt.Logger.WARNING)
TRT_MAIN_VERSION = int(trt.__version__[0])


def build_engine(uff_model_path, trt_engine_datatype, batch_size, workspace, model_width, model_height):
    with trt.Builder(TRT_LOGGER) as builder, \
            builder.create_network() as network, \
            builder.create_builder_config() as config, \
            trt.UffParser() as uff_parser, \
            trt.Runtime(TRT_LOGGER) as runtime:
        if TRT_MAIN_VERSION < 8:
            config.max_workspace_size = workspace * (1 << 20)
        else:
            config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace * (1 << 20))
        if trt_engine_datatype == trt.DataType.HALF:
            config.set_flag(trt.BuilderFlag.FP16)
        builder.max_batch_size = batch_size

        assert uff_parser.register_input("Input", (3, model_width, model_height), trt.tensorrt.UffInputOrder.NCHW)
        assert uff_parser.register_output("MarkOutput_0")
        assert uff_parser.parse(uff_model_path, network)

        if TRT_MAIN_VERSION < 8:
            return builder.build_engine(network, config)
        else:
            plan = builder.build_serialized_network(network, config)
            return runtime.deserialize_cuda_engine(plan)


def save_engine(engine, engine_dest_path):
    os.makedirs(os.path.dirname(engine_dest_path), exist_ok=True)
    buf = engine.serialize()
    with open(engine_dest_path, 'wb') as f:
        f.write(buf)


def load_engine(trt_runtime, engine_path):
    with open(engine_path, 'rb') as f:
        engine_data = f.read()
    engine = trt_runtime.deserialize_cuda_engine(engine_data)
    return engine


TRT_PRECISION_TO_DATATYPE = {
    16: trt.DataType.HALF,
    32: trt.DataType.FLOAT
}

if __name__ == '__main__':
    # Define script command line arguments
    parser = argparse.ArgumentParser(description='Utility to build TensorRT engine prior to inference.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-i', "--input",
                        dest='uff_model_path', metavar='UFF_MODEL_PATH', required=True,
                        help='preprocessed TensorFlow model in UFF format')
    parser.add_argument('-p', '--precision', type=int, choices=[32, 16], default=32,
                        help='desired TensorRT float precision to build an engine')
    parser.add_argument('-b', '--batch-size', type=int, default=1,
                        help='max TensorRT engine batch size')
    parser.add_argument("-w", "--workspace", default=1024, type=int,
                        help="The max memory workspace size to allow in Mb")
    parser.add_argument('-mw', '--model-width', type=int, default=300,
                        help='SSD model width')
    parser.add_argument('-mh', '--model-height', type=int, default=300,
                        help='SSD model height')
    parser.add_argument("-o", "--output", dest='trt_engine_path',
                        help="path of the output file",
                        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine.trt"))

    # Parse arguments passed
    args = parser.parse_args()

    # Build TensorRT engine
    print("Building TensorRT engine. This may take a few minutes.")
    trt.init_libnvinfer_plugins(TRT_LOGGER, '')
    trt_engine = build_engine(
        uff_model_path=args.uff_model_path,
        trt_engine_datatype=TRT_PRECISION_TO_DATATYPE[args.precision],
        batch_size=args.batch_size, workspace=args.workspace,
        model_width=args.model_width, model_height=args.model_height)
    if trt_engine is not None:
        # Save the engine to file
        save_engine(trt_engine, args.trt_engine_path)
        print("TensorRT engine saved to {}".format(args.trt_engine_path))
