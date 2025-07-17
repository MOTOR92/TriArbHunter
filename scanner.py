#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TriArbHunter: мониторинг треугольных арбитражных возможностей на Uniswap V2
"""
import os
import sys
import asyncio
import argparse
from decimal import Decimal, getcontext

from web3 import Web3
from dotenv import load_dotenv
from tabulate import tabulate

# Увеличим точность расчётов
getcontext().prec = 28

# Загрузка переменных окружения из .env
load_dotenv()
INFURA_URL = os.getenv("INFURA_URL")
if not INFURA_URL:
    print("Ошибка: задайте INFURA_URL в окружении (например, в файле .env).")
    sys.exit(1)

# Подключаемся к ноде
w3 = Web3(Web3.HTTPProvider(INFURA_URL))
if not w3.isConnected():
    print("Не удалось подключиться к Ethereum-ноду.")
    sys.exit(1)

# ABI для фабрики и пар Uniswap V2 (минимальный)
FACTORY_ADDRESS = Web3.toChecksumAddress("0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f")
FACTORY_ABI = [
    {
        "constant": True,
        "inputs": [
            {"name": "tokenA", "type": "address"},
            {"name": "tokenB", "type": "address"}
        ],
        "name": "getPair",
        "outputs": [{"name": "pair", "type": "address"}],
        "type": "function"
    }
]
PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"}
        ],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    }
]
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]

factory = w3.eth.contract(address=FACTORY_ADDRESS, abi=FACTORY_ABI)

# Стандартные токены по умолчанию
TOKEN_ADDRESSES = {
    "WETH": Web3.toChecksumAddress("0xC02aaa39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
    "DAI":  Web3.toChecksumAddress("0x6B175474E89094C44Da98b954EedeAC495271d0F"),
    "USDC": Web3.toChecksumAddress("0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")
}

FEE_RATE = Decimal("0.997")  # комиссия 0.3%

async def fetch_reserves(tokenA, tokenB):
    """Возвращает (reserveA, reserveB) как Decimal."""
    pair_addr = factory.functions.getPair(tokenA, tokenB).call()
    if pair_addr == "0x0000000000000000000000000000000000000000":
        raise ValueError("Пара не найдена на Uniswap V2")
    pair = w3.eth.contract(address=pair_addr, abi=PAIR_ABI)
    res = pair.functions.getReserves().call()
    t0 = pair.functions.token0().call()
    # Определяем, какой резервы кому соответствует
    if t0.lower() == tokenA.lower():
        ra, rb = res[0], res[1]
    else:
        ra, rb = res[1], res[0]
    # Узнаем decimals
    decA = w3.eth.contract(address=tokenA, abi=ERC20_ABI).functions.decimals().call()
    decB = w3.eth.contract(address=tokenB, abi=ERC20_ABI).functions.decimals().call()
    return (
        Decimal(ra) / (10 ** decA),
        Decimal(rb) / (10 ** decB)
    )

def compute_amount_out(amount_in, reserve_in, reserve_out):
    """AMM формула с учётом комиссии."""
    amount_in_with_fee = amount_in * FEE_RATE
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in + amount_in_with_fee
    return numerator / denominator

async def scan_triangular(tokens, threshold):
    """Сканируем все упорядоченные тройки (A→B→C→A)."""
    results = []
    for A in tokens:
        for B in tokens:
            for C in tokens:
                if len({A, B, C}) < 3:
                    continue
                try:
                    rAB = await fetch_reserves(A, B)
                    rBC = await fetch_reserves(B, C)
                    rCA = await fetch_reserves(C, A)
                    # Стартуем с 1.0 A
                    amt1 = compute_amount_out(Decimal(1), *rAB)  # A→B
                    amt2 = compute_amount_out(amt1, *rBC)        # B→C
                    amt3 = compute_amount_out(amt2, *rCA)        # C→A
                    profit = amt3 - Decimal(1)
                    if profit > threshold:
                        results.append({
                            "path": f"{A}→{B}→{C}→{A}",
                            "profit": float(profit)
                        })
                except Exception as e:
                    # Игнорируем несуществующие пары
                    continue
    return results

async def main():
    parser = argparse.ArgumentParser(
        description="TriArbHunter: ищет треугольный арбитраж в реальном времени"
    )
    parser.add_argument(
        "--tokens", nargs="+", default=list(TOKEN_ADDRESSES.keys()),
        help="Перечень токенов (DNA), например WETH DAI USDC"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.001,
        help="Минимальная прибыль (в долях), чтобы вывести сигнал"
    )
    parser.add_argument(
        "--interval", type=int, default=15,
        help="Интервал опроса в секундах"
    )
    args = parser.parse_args()

    # Преобразуем символы в адреса
    try:
        token_addrs = [TOKEN_ADDRESSES[sym] for sym in args.tokens]
    except KeyError as e:
        print(f"Неизвестный токен: {e}")
        sys.exit(1)

    print(f"Запуск сканера для {args.tokens}, порог прибыли = {args.threshold*100:.2f}%...")
    while True:
        res = await scan_triangular(token_addrs, Decimal(args.threshold))
        if res:
            table = tabulate(
                [(r["path"], f"{r['profit']*100:.4f}%") for r in res],
                headers=["Путь арбитража", "Прибыль"],
                tablefmt="github"
            )
            print(table)
        else:
            print("Возможных арбитражей не найдено.")
        await asyncio.sleep(args.interval)

if __name__ == "__main__":
    asyncio.run(main())
