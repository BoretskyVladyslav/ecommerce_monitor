import asyncio
import pandas as pd
from datetime import datetime
import os
from database.db_manager import DatabaseManager
from config.logger import setup_logger

logger = setup_logger("ReportGenerator")

class ReportGenerator:
    def __init__(self):
        self.db = DatabaseManager()
        self.report_dir = "reports"
        os.makedirs(self.report_dir, exist_ok=True)

    async def fetch_data(self):
        """Fetches product status data joining products and product_options."""

        pool = await self.db.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                
                query_main = """
                    SELECT 
                        p.id as product_id, 
                        p.original_url, 
                        po.option_name_1 as option_name,
                        po.status as option_status,
                        po.price_sale as option_price
                    FROM products p
                    JOIN product_options po ON p.id = po.product_id
                """
                await cursor.execute(query_main)
                columns = [desc[0] for desc in cursor.description]
                rows = await cursor.fetchall()
                df_main = pd.DataFrame(rows, columns=columns)

                try:
                    query_logs = "SELECT * FROM products_log ORDER BY id DESC LIMIT 1000"
                    await cursor.execute(query_logs)
                    log_cols = [desc[0] for desc in cursor.description]
                    log_rows = await cursor.fetchall()
                    df_logs = pd.DataFrame(log_rows, columns=log_cols)
                except Exception as e:
                    logger.warning(f"Could not fetch logs (table might be missing): {e}")
                    df_logs = pd.DataFrame()

                return df_main, df_logs

    async def generate(self):
        """Generates the Excel report."""
        try:
            df_main, df_logs = await self.fetch_data()
            
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"Report_{timestamp}.xlsx"
            filepath = os.path.join(self.report_dir, filename)

            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                df_main.to_excel(writer, sheet_name='Products Status', index=False)
                if not df_logs.empty:
                    df_logs.to_excel(writer, sheet_name='Logs', index=False)

            return filepath
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            raise

if __name__ == "__main__":
    async def test():
        rg = ReportGenerator()
        print(await rg.generate())
    asyncio.run(test())
