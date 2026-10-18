"""The live section suggester (spec 2.7; plan PR 9, R9, R22): Super through the gateway. It
lives with the API, not in `sections/`, which stays free of prompts and model clients.

One call per propose (job `section_suggestion`, prompt `section_suggestion/v1`), validated by the
same response schema as every suggester; code then checks each suggestion (`check_suggestions`).
The call is refused before it is sent when its estimate, with its one validation retry, exceeds
`section_suggest_cap_usd` (R22: per propose call). It is outside any run, so it writes a ledger
line (use `development`, through the gateway) and no ModelCall record; its request and response
go to the structured log (R9). Any failure gives no suggestions: the rule cut stands.
"""

from guideword.api.models import SectionSuggestion
from guideword.config import Config
from guideword.gateway.client import Gateway
from guideword.gateway.estimate import estimate_cost
from guideword.gateway.prompts import as_data, load_prompt, render
from guideword.logs import get_logger
from guideword.runs.estimate import ATTEMPTS, calls_usd
from guideword.schema.enums import Tier
from guideword.schema.plant import Plant
from guideword.schema.records import Section
from guideword.sections.suggest import SuggestionResponse, parse_response

JOB = "section_suggestion"
ASK = (
    "Suggest changes to the section cut and a purpose for each section, "
    "in the required JSON schema."
)

log = get_logger(__name__)


class GatewaySuggester:
    def __init__(self, gateway: Gateway, config: Config) -> None:
        self.gateway = gateway
        self.config = config
        self.prompt = load_prompt(JOB, config)

    def messages(self, plant: Plant, sections: list[Section]) -> list[dict[str, str]]:
        system = render(
            self.prompt.body,
            {
                # as data: plant notes cannot close a block (CLAUDE.md §3)
                "plant": as_data(plant.model_dump(mode="json", exclude_none=True)),
                "sections": as_data([s.model_dump(mode="json") for s in sections]),
            },
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": ASK}]

    def suggest(self, plant: Plant, sections: list[Section]) -> list[SectionSuggestion]:
        messages = self.messages(plant, sections)
        max_tokens = self.config.caps.run.max_tokens[JOB]
        prices = self.config.models.tiers[Tier(self.config.routing.jobs[JOB])]
        first = estimate_cost(prices, messages, None, max_tokens)
        usd = calls_usd(prices, first.input_tokens, max_tokens, ATTEMPTS)
        cap = self.config.caps.plant.section_suggest_cap_usd
        if usd > cap:
            log.warning(
                "section suggestion refused: over its cap",
                extra={"context": {"estimate_usd": round(usd, 6), "cap_usd": cap}},
            )
            return []
        result = self.gateway.call(
            job=JOB, prompt_version=self.prompt.label, messages=messages, schema=SuggestionResponse
        )
        log.info(
            "section suggestion call",
            extra={
                "context": {
                    "outcome": result.outcome,
                    "cost_usd": result.cost_usd,
                    "request": messages,
                    "response": result.content,
                }
            },
        )
        if result.outcome != "ok" or not isinstance(result.value, SuggestionResponse):
            return []
        return parse_response(result.value.model_dump())
