# DEGIRO integration laboratory

Open **Mehr → DEGIRO**, select a scenario and tap **Automatischen Simulationslauf testen**.
The authenticated `/api/degiro/sandbox` endpoint replays fixed synthetic EUR product
quotes using the existing simulation engine. An isolated `PaperAdapter` consumes
simulated buy, trailing-stop and sell events. It rejects duplicate-key conflicts,
overselling, invalid prices and stop loosening. Repeated identical events return
the original receipt without another position change. Every receipt is marked
`brokerSubmitted: false` and uses a `SIM-` identifier.

This is an internal adapter contract, NOT DEGIRO's request format. No
`degiro-connector` dependency, login, credentials, outbound broker connection,
real orders or continuous background process are implemented. A green test
result is only an internal test result. The engine's existing assumptions and
risk limits are unchanged. Results are ephemeral and synthetic, not evidence
of live profitability or connectivity. Existing product and trade tabs stay put.

No additional paid service or library is required. Existing hosting costs are
unaffected. An unanswered permission email does not establish broker approval.
Any real connector integration needs separate review of authorization, SDK
compatibility, instruments, account permissions and operational behavior.

Verification: `python -m unittest test_degiro_sandbox test_vollautomatisch_engine test_broker_bridge`
