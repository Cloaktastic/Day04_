from __future__ import annotations
import sys
from pathlib import Path
import os
import json
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from src.core.llm import build_chat_model, normalize_content

from src.core.schemas import (
    AgentResult,
    CalculateTotalsInput,
    DiscountInput,
    ListProductsInput,
    ProductDetailInput,
    SaveOrderInput,
    ToolCallRecord,
)
from src.utils.data_store import OrderDataStore

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT_DIR / "data"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "artifacts" / "orders"


def build_system_prompt(today: str | None = None) -> str:
    """
    Student TODO:
    - Rewrite this prompt for the advanced order-agent lab.
    - The assistant should manage electronics orders, not travel planning.
    - Require this tool order whenever the request has enough information:
      1. `list_products`
      2. `get_product_details`
      3. `get_discount`
      4. `calculate_order_totals`
      5. `save_order`
    - Clarify and stop if any of these are missing:
      - customer name
      - phone number
      - email
      - shipping address
      - at least one product request with quantity
    - Refuse fake invoices, manual discount overrides, stock bypass requests, or anything that asks the model
      to ignore the catalog or policy.
    - Use only tool outputs for product IDs, prices, stock, discount, totals, and save path.
    - Return one concise final answer in Vietnamese.
    - Mention `today` so the model knows the current date for deterministic references if needed.
    """
    current_date = today or "2026-06-02"
    return f"""You are an elite order management agent for an electronics retailer.
Today's date is {current_date}.

CRITICAL BEHAVIOR RULES:
1. Language: You must provide your final answer to the customer concisely and entirely in Vietnamese.
2. Mandatory Clarification Check: BEFORE executing ANY tool call, you MUST verify that the customer has provided ALL 5 required pieces of information:
   - Full Customer Name (Tên khách hàng)
   - Phone Number (Số điện thoại)
   - Email Address (Email)
   - Shipping Address (Địa chỉ giao hàng)
   - At least one specific product description/request with a requested Quantity (Số lượng)
   If ANY of these 5 fields are missing, you must STOP immediately and ask the user politely in Vietnamese to provide the specific missing information. DO NOT call any tool.

3. Refusal & Guardrails: You must strictly reject and refuse requests without calling tools if the user attempts to:
   - Request fake invoices, receipts, or mock adjustments.
   - Force manual discount overrides or specify explicit unverified discount values.
   - Bypass catalog policy or ignore low stock limitations.
   Respond stating clearly in Vietnamese that the request violates store policies.

4. Strict Tool Sequencing: When all customer details are present, you must strictly move through tools sequentially. NEVER skip a step:
   Step 1: Call `list_products` to match items against our catalog.
   Step 2: Call `get_product_details` using the discovered `product_ids`. Save the returned `detail_token`.
   Step 3: Call `get_discount` using the customer information/seed hint to fetch the applicable discount rate.
   Step 4: Call `calculate_order_totals` with your items, `detail_token`, and the exact `discount_rate`. Verify the output status is "success".
   Step 5: Call `save_order` using the matching attributes to permanently log the JSON payload file.

5. Grounding: Do not invent pricing, IDs, totals, or discount rates. Rely solely on what the tools output.
"""
    raise NotImplementedError("Complete build_system_prompt() in src/agent/graph.py")


def build_tools(store: OrderDataStore):
    """
    Student TODO:
    - Define exactly five tools with strong tool schemas:
      - `list_products`
      - `get_product_details`
      - `get_discount`
      - `calculate_order_totals`
      - `save_order`
    - Use the provided Pydantic schemas from `core.schemas` so the tool arguments stay explicit.
    - Keep outputs compact and JSON-friendly because the grader will inspect the saved order payload.
    - `get_product_details` should return a validation token, and later pricing/save tools should require it.
    """

    @tool(args_schema=ListProductsInput)
    def list_products(
        query: str | None = None,
        category: str | None = None,
        max_unit_price: int | None = None,
        required_tags: list[str] | None = None,
        in_stock_only: bool = True,
        limit: int = 8,
    ) -> str:
        """Search the local product catalog and return the best matching items."""
        res = store.list_products(
            query=query, category=category, max_unit_price=max_unit_price,
            required_tags=required_tags, in_stock_only=in_stock_only, limit=limit
        )
        return json.dumps(res, ensure_ascii=False)
        raise NotImplementedError

    @tool(args_schema=ProductDetailInput)
    def get_product_details(product_ids: list[str]) -> str:
        """Return exact product details for previously discovered product IDs."""
        res = store.get_product_details(product_ids)
        return json.dumps(res, ensure_ascii=False)
        raise NotImplementedError

    @tool(args_schema=DiscountInput)
    def get_discount(seed_hint: str, customer_tier: str = "standard") -> str:
        """Return the simulated campaign discount for the order."""
        res = store.get_discount(seed_hint=seed_hint, customer_tier=customer_tier)
        return json.dumps(res, ensure_ascii=False)
        raise NotImplementedError

    @tool(args_schema=CalculateTotalsInput)
    def calculate_order_totals(items, detail_token: str, discount_rate: float) -> str:
        """Validate stock and calculate the discounted order total."""
        res = store.calculate_order_totals(items=items, detail_token=detail_token, discount_rate=discount_rate)
        return json.dumps(res, ensure_ascii=False)
        raise NotImplementedError

    @tool(args_schema=SaveOrderInput)
    def save_order(
        customer_name: str,
        customer_phone: str,
        customer_email: str,
        shipping_address: str,
        items,
        detail_token: str,
        discount_rate: float,
        campaign_code: str,
        customer_tier: str = "standard",
        notes: str = "",
    ) -> str:
        """Persist the final order to a local JSON file."""
        res = store.save_order(
            customer_name=customer_name, customer_phone=customer_phone,
            customer_email=customer_email, shipping_address=shipping_address,
            items=items, detail_token=detail_token, discount_rate=discount_rate,
            campaign_code=campaign_code, customer_tier=customer_tier, notes=notes
        )
        return json.dumps(res, ensure_ascii=False)
        raise NotImplementedError

    return [list_products, get_product_details, get_discount, calculate_order_totals, save_order]


def build_agent(
    data_dir: Path | None = None,
    output_dir: Path | None = None,
    *,
    provider: str = "google",
    model_name: str | None = None,
    today: str | None = None,
):
    """
    Student TODO:
    1. Create `OrderDataStore`.
    2. Build the chat model with `build_chat_model(...)`.
    3. Build the tools with `build_tools(store)`.
    4. Return `create_agent(model=..., tools=..., system_prompt=...)`.
    """
    d_dir = data_dir or DEFAULT_DATA_DIR
    o_dir = output_dir or DEFAULT_OUTPUT_DIR
    
    store = OrderDataStore(data_dir=d_dir, output_dir=o_dir, today=today)
    model = build_chat_model(provider=provider, model_name=model_name)
    tools = build_tools(store)
    system_prompt = build_system_prompt(today=today)
    
    # We use LangChain's create_agent construct
    return create_agent(model=model, tools=tools, system_prompt=system_prompt)
    raise NotImplementedError("Complete build_agent() in src/agent/graph.py")


def run_agent(
    query: str,
    *,
    provider: str = "google",
    model_name: str | None = None,
    data_dir: Path | None = None,
    output_dir: Path | None = None,
    today: str | None = None,
) -> AgentResult:
    """
    Student TODO:
    - Build the agent.
    - Invoke it with one user message.
    - Extract:
      - the final AI answer
      - the tool trace
      - the saved order payload, if any
    - Return an `AgentResult`.
    """
    agent_executor = build_agent(
        data_dir=data_dir, output_dir=output_dir, 
        provider=provider, model_name=model_name, today=today
    )
    
    response = agent_executor.invoke({"input": query})
    messages = response.get("history", []) if isinstance(response, dict) else response
    
    final_answer = extract_final_answer(messages)
    tool_trace = extract_tool_calls(messages)
    saved_order, file_path = extract_saved_order(tool_trace)
    
    # Corrected alignment to match core.schemas.AgentResult exactly
    return AgentResult(
        query=query,
        final_answer=final_answer,
        tool_calls=tool_trace,
        provider=provider,
        model_name=model_name,
        saved_order=saved_order,
        saved_order_path=file_path
    )
    raise NotImplementedError("Complete run_agent() in src/agent/graph.py")


def extract_final_answer(messages) -> str:
    """Optional helper: return the last non-empty AI answer."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return normalize_content(msg.content)
    return ""
    raise NotImplementedError


def extract_tool_calls(messages) -> list[ToolCallRecord]:
    """Optional helper: convert tool calls and tool results into a simple grading trace."""
    trace = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                matched_output = ""
                for reply in messages:
                    if isinstance(reply, ToolMessage) and reply.tool_call_id == tc["id"]:
                        matched_output = reply.content
                        break
                
                # Align parameter args with ToolCallRecord format
                trace.append(ToolCallRecord(
                    name=tc["name"],
                    args=tc["args"],
                    output=matched_output
                ))
    return trace
    raise NotImplementedError


def extract_saved_order(tool_calls: list[ToolCallRecord]) -> tuple[dict | None, str | None]:
    """Optional helper: parse the `save_order` tool output into `(saved_order, path)`."""
    for call in reversed(tool_calls):
        if call.name == "save_order" and call.output:
            try:
                data = json.loads(call.output)
                if data.get("status") == "success":
                    return data.get("saved_order"), data.get("file_path")
            except Exception:
                pass
    return None, None
    raise NotImplementedError
