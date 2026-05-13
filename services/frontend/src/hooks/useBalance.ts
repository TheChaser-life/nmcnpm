/**
 * useBalance.ts
 *
 * Hook quản lý số dư và lịch sử giao dịch của user.
 * Task 6.2.4 — Hiển thị số dư hiện tại và lịch sử giao dịch.
 */

import { useState, useEffect, useCallback } from 'react'
import { getBalance, type BalanceInfo, type TransactionRecord } from '../services/moneyService'

interface UseBalanceReturn {
  balanceVnd: number | null
  transactions: TransactionRecord[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useBalance(): UseBalanceReturn {
  const [balanceVnd, setBalanceVnd] = useState<number | null>(null)
  const [transactions, setTransactions] = useState<TransactionRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchBalance = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data: BalanceInfo = await getBalance()
      setBalanceVnd(data.balance_vnd)
      setTransactions(data.transactions ?? [])
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Không thể tải số dư'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchBalance()
  }, [fetchBalance])

  return {
    balanceVnd,
    transactions,
    loading,
    error,
    refresh: fetchBalance,
  }
}
