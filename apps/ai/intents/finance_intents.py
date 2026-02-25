"""
Finance Intent Definitions

OpenAI function (tool) definitions for finance-related actions:
- log_transaction: Record a financial transaction
- check_budget: Query budget status for a category or overall
"""

FINANCE_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_transaction",
            "description": "Log a financial transaction (expense or income). Use when user mentions spending money, buying something, paying a bill, receiving income, or any financial transaction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "Transaction amount. Positive for income, negative for expenses. If user says 'spent $50', use -50."
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of the transaction (e.g., 'Groceries at Walmart', 'Paycheck')"
                    },
                    "category": {
                        "type": "string",
                        "description": "Category name (e.g., 'Groceries', 'Dining', 'Gas', 'Income', 'Entertainment'). Infer from context."
                    },
                    "account": {
                        "type": "string",
                        "description": "Account name (e.g., 'Checking', 'Credit Card'). Optional — uses default if not specified."
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any additional notes"
                    }
                },
                "required": ["amount", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_budget",
            "description": "Check budget status. Use when user asks about their budget, spending, how much they've spent, or remaining budget.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Specific budget category to check (e.g., 'Groceries', 'Dining'). If not specified, returns overall summary."
                    },
                    "month": {
                        "type": "string",
                        "description": "Month to check (e.g., 'February', 'this month'). Defaults to current month."
                    }
                },
                "required": []
            }
        }
    },
]
