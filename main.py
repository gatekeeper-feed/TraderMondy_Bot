name: Trader Mondy Engine

on:
  schedule:
    - cron: "*/15 * * * *"
    - cron: "30 2 * * 1-5"
    - cron: "30 10 * * 1-5"
  workflow_dispatch:
    inputs:
      mode:
        description: "What to run"
        type: choice
        default: test
        options:
          - test
          - signals
          - premarket
          - postmarket

permissions:
  contents: write

concurrency:
  group: tradermondy
  cancel-in-progress: false

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install packages
        run: pip install -r requirements.txt

      - name: Run engine
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          EVENT_NAME: ${{ github.event_name }}
          SCHEDULE: ${{ github.event.schedule }}
          INPUT_MODE: ${{ github.event.inputs.mode }}
        run: python main.py

      - name: Save state
        run: |
          git config user.name "TraderMondy Bot"
          git config user.email "bot@users.noreply.github.com"
          git add state.json
          git diff --cached --quiet && exit 0
          git commit -m "Update state"
          git pull --rebase
          git push
