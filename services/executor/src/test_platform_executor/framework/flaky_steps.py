import random

from test_platform_executor.framework.artifacts import ArtifactStrategy, NoArtifactStrategy
from test_platform_executor.framework.context import StepContext
from test_platform_executor.framework.step_decorator import step
from test_platform_executor.framework.steps import StepFailedError

# ~40% fail rate (within the 30–50% demo band)
_FAIL_PROBABILITY = 0.4


@step("coin_flip")
class CoinFlipStep:
    """Demo step that fails randomly so history/flakiness UI has fail data."""

    def __init__(
        self,
        fail_probability: float = _FAIL_PROBABILITY,
        artifact_strategy: ArtifactStrategy | None = None,
    ) -> None:
        self._fail_probability = fail_probability
        self.artifact_strategy = artifact_strategy or NoArtifactStrategy()

    def execute(self, context: StepContext) -> None:
        with context.log.scope(
            "domain",
            "Flip the demo coin",
            component="coin_flip",
            event="coin.flip",
            data={"fail_probability": self._fail_probability},
        ):
            with context.timed_action():
                roll = random.random()
                context.set("coin_roll", roll)
                if roll < self._fail_probability:
                    raise StepFailedError(
                        self.id,
                        "coin landed on tails (simulated flake)",
                    )
            context.log.log(
                "domain",
                "Coin landed on heads",
                component="coin_flip",
                event="coin.heads",
                data={"roll": context.get("coin_roll")},
            )
