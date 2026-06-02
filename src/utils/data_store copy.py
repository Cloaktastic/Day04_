from __future__ import annotations
import json
import hashlib
from pathlib import Path
from src.core.schemas import OrderLineInput, ProductRecord


class OrderDataStore:
    """
    Student TODO:
    - Load `products.json`.
    - Build lookup helpers for product IDs and normalized search.
    - Save final orders under `artifacts/orders/`.
    """

    def __init__(self, data_dir: Path, output_dir: Path, *, today: str | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.today = today
        self.products: list[ProductRecord] = []
        self.product_index: dict[str, ProductRecord] = {}

        catalog_path = self.data_dir / "products.json"
        if catalog_path.exists():
            with open(catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data.get("products", data) if isinstance(data, dict) else data
                
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    
                    # Robust Key Matching: Extracts whichever structural variant is present
                    pid = item.get("product_id") or item.get("id")
                    if not pid:
                        continue
                        
                    sku_val = item.get("sku") or f"SKU-{pid}"
                    price_val = item.get("unit_price") or item.get("price", 0)
                    warranty_val = item.get("warranty_months") or item.get("warranty", 12)
                    
                    prod = ProductRecord(
                        product_id=str(pid),
                        sku=str(sku_val),
                        name=item.get("name", "Unknown Product"),
                        brand=item.get("brand", "Generic"),
                        category=item.get("category", "General"),
                        unit_price=int(price_val),
                        stock=item.get("stock", 0),
                        warranty_months=int(warranty_val),
                        tags=item.get("tags", []),
                        description=item.get("description", "")
                    )
                    self.products.append(prod)
                    # Use product_id for index lookup transparency
                    self.product_index[prod.product_id] = prod
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        #raise NotImplementedError("Load product data and output paths in OrderDataStore.__init__().")
    
    def _generate_token(self, product_ids: list[str]) -> str:
        """Helper function to generate a deterministic verification token."""
        sorted_ids = sorted(product_ids)
        seed = f"token-salt-{','.join(sorted_ids)}"
        return hashlib.md5(seed.encode("utf-8")).hexdigest()
    
    def list_products(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        max_unit_price: int | None = None,
        required_tags: list[str] | None = None,
        in_stock_only: bool = True,
        limit: int = 8,
    ) -> list[dict]:
        """
        Student TODO:
        - Search by product name, brand, category, tags, and description.
        - Return compact catalog summaries that the model can reuse in later tool calls.
        """
        results = []
        q = query.lower() if query else None
        for p in self.products:
            if in_stock_only and p.stock <= 0:
                continue
            if category and p.category.lower() != category.lower():
                continue
            if max_unit_price and p.unit_price > max_unit_price:
                continue
            if required_tags:
                if not all(t in p.tags for t in required_tags):
                    continue
            if q:
                match = (q in p.name.lower() or 
                         q in p.brand.lower() or 
                         q in p.description.lower() or 
                         any(q in t.lower() for t in p.tags))
                if not match:
                    continue
                    
            results.append({
                "id": p.product_id,
                "name": p.name,
                "brand": p.brand,
                "category": p.category,
                "price": p.unit_price,
                "stock": p.stock
            })
            if len(results) >= limit:
                break
        return results
        raise NotImplementedError


    def get_product_details(self, product_ids: list[str]) -> list[dict]:
        """
        Student TODO:
        - Return exact pricing, stock, category, and warranty information for each product ID.
        - Return a deterministic validation token that later tools can verify.
        - Preserve the input order or document how you reorder it.
        """
        matched = []
        for pid in product_ids:
            if pid in self.product_index:
                p = self.product_index[pid]
                matched.append({
                    "id": p.product_id, 
                    "name": p.name,
                    "price": p.unit_price,
                    "stock": p.stock,
                    "category": p.category
                })
        
        token = self._generate_token(product_ids)
        return {
            "products": matched,
            "detail_token": token,
            "status": "success" if matched else "empty"
        }
        raise NotImplementedError

    def get_discount(self, *, seed_hint: str, customer_tier: str = "standard") -> dict:
        """
        Student TODO:
        - Simulate a random campaign discount with deterministic seeding for grading.
        - Supported discount rates should be `0.1` or `0.2`.
        """
        score = sum(ord(c) for c in seed_hint)
        discount_rate = 0.2 if score % 2 == 0 else 0.1
        campaign_code = f"CAMP-{score % 1000:03d}"
        return {
            "discount_rate": discount_rate,
            "campaign_code": campaign_code,
            "status": "success"
        }
        raise NotImplementedError

    def calculate_order_totals(self, *, items: list[OrderLineInput], detail_token: str, discount_rate: float) -> dict:
        """
        Student TODO:
        - Validate product IDs.
        - Validate the detail token produced by `get_product_details(...)`.
        - Validate requested quantities against stock.
        - Compute subtotal, discount amount, and final total.
        - Return an error payload instead of throwing for common user mistakes.
        """
        # Re-verify token security bounds
        p_ids = [
            item.product_id if not isinstance(item, dict) else item.get('product_id') 
            for item in items
        ]
        expected_token = self._generate_token(p_ids)
        
        if detail_token != expected_token:
            return {"status": "error", "message": "Invalid or expired verification detail_token."}
            
        subtotal = 0
        line_items = []
        
        for item in items:
            pid = item.product_id if not isinstance(item, dict) else item.get('product_id')
            qty = item.quantity if not isinstance(item, dict) else item.get('quantity', 0)
            
            if pid not in self.product_index:
                return {"status": "error", "message": f"Product {pid} not found in store catalog."}
            
            prod = self.product_index[pid]
            if prod.stock < qty:
                return {"status": "error", "message": f"Insufficient stock for {prod.name}. Available: {prod.stock}."}
                
            line_cost = prod.unit_price * qty
            subtotal += line_cost
            line_items.append({
                "product_id": pid,
                "name": prod.name,
                "quantity": qty,
                "unit_price": prod.unit_price,
                "total_price": line_cost
            })
            
        discount_amount = int(subtotal * discount_rate)
        final_total = subtotal - discount_amount
        
        return {
            "status": "success",
            "subtotal": subtotal,
            "discount_amount": discount_amount,
            "final_total": final_total,
            "items": line_items
        }
        raise NotImplementedError

    def save_order(
        self,
        *,
        customer_name: str,
        customer_phone: str,
        customer_email: str,
        shipping_address: str,
        items: list[OrderLineInput],
        detail_token: str,
        discount_rate: float,
        campaign_code: str,
        customer_tier: str = "standard",
        notes: str = "",
    ) -> dict:
        """
        Student TODO:
        - Recompute totals before saving.
        - Build a deterministic order ID.
        - Persist the final JSON payload to the output directory.
        - Return both the saved order payload and the saved file path.
        """
        totals = self.calculate_order_totals(items=items, detail_token=detail_token, discount_rate=discount_rate)
        if totals["status"] != "success":
            return totals

        seed_str = f"{customer_phone}-{self.today}-{totals['final_total']}"
        order_id = f"ORD-{hashlib.md5(seed_str.encode('utf-8')).hexdigest()[:8].upper()}"
        
        payload = {
            "order_id": order_id,
            "customer": {
                "name": customer_name,
                "phone": customer_phone,
                "email": customer_email,
                "shipping_address": shipping_address,
                "tier": customer_tier
            },
            "items": totals["items"],
            "totals": {
                "subtotal": totals["subtotal"],
                "discount_rate": discount_rate,
                "discount_amount": totals["discount_amount"],
                "final_total": totals["final_total"]
            },
            "campaign_code": campaign_code,
            "notes": notes,
            "created_at": self.today
        }
        
        file_path = self.output_dir / f"{order_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            
        return {
            "status": "success",
            "saved_order": payload,
            "file_path": str(file_path)
        }
        raise NotImplementedError
