# Final Project — CareerMirror

CareerMirror is a Thai-language career guidance application for IT job seekers. It combines profile assessment, role matching, retrieval-augmented answers, salary references and market data.

## Source repository

[CareerMirror team repository](https://github.com/sakda1306/Advanced-Topic-in-Computer-Software-Course-Career-Mirror)

Submitted by Sakda Baokham (116730462016-0).

Source snapshot [5095ea0c3a9c](https://github.com/sakda1306/Advanced-Topic-in-Computer-Software-Course-Career-Mirror/commit/5095ea0c3a9c5fcfc28f3c52c3041ac6f6859c69).

## Run locally

Copy .env.example to .env and configure the required values, then run:

```sh
docker compose up --build
```

See [API setup](api/README.md), [web setup](web/README.md), [requirements](docs/PRD.md), and [architecture](docs/Design.md).

## Evaluation

The [router evaluation dataset](api/tests/router/router200_th.jsonl) contains 200 cases. The [benchmark documentation](benchmarks/careermirror_v2/README.md) describes the broader evaluation set.
