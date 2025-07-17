# TriArbHunter

TriArbHunter — утилита для мониторинга треугольных арбитражных возможностей на Uniswap V2 в реальном времени.

## Возможности

- Поддержка любых трёх токенов (по умолчанию WETH, DAI, USDC)
- Расчёт прибыли с учётом комиссии 0.3%
- CLI-параметры: интервал, порог прибыли, список токенов
- Красивый вывод в табличном виде

## Требования

- Python 3.9+
- Infura API ключ (переменная окружения `INFURA_URL`)

## Установка

```bash
git clone https://github.com/yourusername/TriArbHunter.git
cd TriArbHunter
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
