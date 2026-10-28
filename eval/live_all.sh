#!/bin/sh
# Полный живой прогон с моделью из .env: связь → тесты → сценарии → ответы и утечки → диалоги → симуляция.
#     make live            # или: sh eval/live_all.sh
# Результаты — eval/live_<дата>/ (журнал run.log и JSON каждого этапа) плюс отчёты eval/report.md,
# eval/answers_report.md, eval/report_simulate.md. Расходует токены модели: ~15–25 минут, несколько сотен запросов.
set -u
PY=${PY:-.venv/bin/python}
OUT=eval/live_$(date +%Y%m%d_%H%M)
mkdir -p "$OUT"
LOG="$OUT/run.log"
FAILED=""

run() {  # шаг: печать в журнал, время, код выхода (tee его скрывает, поэтому через файл)
    name=$1; shift
    echo "\n===== $name =====" | tee -a "$LOG"
    started=$(date +%s)
    { "$@"; echo $? > "$OUT/.code"; } 2>&1 | tee -a "$LOG"
    code=$(cat "$OUT/.code")
    [ "$code" = 0 ] || FAILED="$FAILED\n  - $name (код $code)"
    echo "----- $name: $(( $(date +%s) - started )) с, код $code" | tee -a "$LOG"
    return "$code"
}

run "Связь с моделью" "$PY" -m tools.llm_check || { echo "Модель недоступна — дальше не идём"; exit 1; }
run "Автономные тесты" "$PY" -m pytest -q
run "Сценарии: правила, модель, сбои модели" "$PY" -m eval.run --modes rules,llm,chaos
run "Ответы модели, RAG, утечки" "$PY" -m eval.answers_live
run "Диалоги (отложенная выборка)" "$PY" -m eval.dialogue_20261027 --set holdout --model --pace-seconds 1 \
    --output "$OUT/dialogue_holdout.json"
run "Перебивания и смена планов" "$PY" -m eval.dialogue_interruptions_20261028 --model --pause 1 \
    --output "$OUT/interruptions.json"
run "Разговорные формулировки" "$PY" -m eval.colloquial_20261028 --model --pace-seconds 1 \
    --output "$OUT/colloquial.json"
run "Матрица параметров" "$PY" -m eval.parameter_matrix_live_20261028 --pause 1 --output "$OUT/parameters.json"
run "Модель играет путешественника" "$PY" -m eval.simulate --agent llm

rm -f "$OUT/.code"
if [ -n "$FAILED" ]; then
    printf "\nНе прошли:%b\n" "$FAILED" | tee -a "$LOG"
    exit 1
fi
echo "\nВсе этапы прошли. Журнал: $LOG" | tee -a "$LOG"
