# FC experiment runner for the Web Lab

This repository implements a backend job runner for the WebLab’s Functional Curation (FC) experiments. It functions as an asynchronous execution service that bridges the WebLab frontend with long-running FC model/protocol runs, then reports status and artifacts back to the frontend.

At a high level, it:

1. Accepts experiment-related requests from a web-facing CGI endpoint.
1. Queues work in [Celery](https://docs.celeryq.dev/).
1. Downloads model/protocol archives (and optional fitting data/specs).
1. Checks protocol-model compatibility.
1. Runs the simulation/fitting executable.
1. Zips results and posts them back to a callback URL.
