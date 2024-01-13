import requests
from fastapi import FastAPI
from ray import serve
import tritonserver
import os
from pprint import pprint
from PIL import Image
import numpy

# 1: Define a FastAPI app and wrap it in a deployment with a route handler.
app = FastAPI()

S3_BUCKET_URL = None

if "S3_BUCKET_URL" in os.environ:
    S3_BUCKET_URL = os.environ["S3_BUCKET_URL"]


def _print_heading(message):
    print("")
    print(message)
    print("-" * len(message))


@serve.deployment(ray_actor_options={"num_gpus": 1})
@serve.ingress(app)
class TritonDeployment:
    def __init__(self):
        self._triton_server = tritonserver

        if S3_BUCKET_URL is not None:
            model_repository = S3_BUCKET_URL
        else:
            model_repository = "/workspace/models"

        self._triton_server = tritonserver.Server(
            model_repository=model_repository,
            model_control_mode=tritonserver.ModelControlMode.EXPLICIT,
            log_info=False,
        )
        self._triton_server.start(wait_until_ready=True)

        _print_heading("Triton Server Started")
        _print_heading("Metadata")
        pprint(self._triton_server.metadata())
        _print_heading("Models")
        pprint(self._triton_server.models())

    @app.get("/test")
    def test(self, name: str) -> str:
        if not self._triton_server.model("test").ready():
            self._test_model = self._triton_server.load("test")

        output = []
        for response in self._test_model.infer(inputs={"string_input": [[name]]}):
            output.append(response.outputs["string_output"].to_string_array()[0][0])

        return "".join(output)

    @app.get("/generate")
    def generate(self, prompt: str, filename: str = "generated_image.jpg") -> None:
        if not self._triton_server.model("stable_diffusion").ready():
            try:
                self._triton_server.load("text_encoder")
                self._triton_server.load("vae")

                self._stable_diffusion = self._triton_server.load("stable_diffusion")
                if not self._stable_diffusion.ready():
                    raise Exception("Model not ready")
            except Exception as error:
                print("Error can't load model!")
                print(
                    f"Please ensure dependencies are met and you have set the environment variable HF_TOKEN {e}"
                )
                return

        for response in self._stable_diffusion.infer(inputs={"prompt": [[prompt]]}):
            generated_image = (
                numpy.from_dlpack(response.outputs["generated_image"])
                .squeeze()
                .astype(numpy.uint8)
            )

            image_ = Image.fromarray(generated_image)
            image_.save(filename)


if __name__ == "__main__":
    # 2: Deploy the deployment.
    serve.run(TritonDeployment.bind(), route_prefix="/")

    # 3: Query the deployment and print the result.
    print(
        requests.get("http://localhost:8000/test", params={"name": "Theodore"}).json()
    )

    # 3: Query the deployment and print the result.
    print(
        requests.get(
            "http://localhost:8000/generate",
            params={"prompt": "Alvin, Simon, Theodore", "filename": "foo.bmp"},
        )
    )

    # "Hello Theodore!"
else:
    triton_app = TritonDeployment.bind()
