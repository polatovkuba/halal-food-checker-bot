import asyncpg
import os
import aiohttp
import ssl
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
pool = None

async def create_pool():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, statement_cache_size=0)
    return pool

async def create_tables():
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                brand VARCHAR(255),
                status VARCHAR(20) DEFAULT 'unknown',
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS check_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                barcode VARCHAR(50),
                product_name VARCHAR(255),
                brand VARCHAR(255),
                status VARCHAR(20),
                checked_at TIMESTAMP DEFAULT NOW()
            );
        """)

async def get_product_by_name(name: str, brand: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM products WHERE LOWER(name) = LOWER($1) AND LOWER(brand) = LOWER($2)",
            name, brand
        )
        return dict(row) if row else None

async def save_history(user_id: int, barcode: str, product_name: str, brand: str, status: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO check_history (user_id, barcode, product_name, brand, status) VALUES ($1, $2, $3, $4, $5)",
            user_id, barcode, product_name, brand, status
        )

async def add_product(name: str, brand: str, status: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO products (name, brand, status) 
            VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING
        """, name, brand, status)

async def get_all_products():
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM products ORDER BY created_at DESC")
        return [dict(row) for row in rows]

async def get_user_history(user_id: int):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM check_history WHERE user_id = $1 ORDER BY checked_at DESC LIMIT 10",
            user_id
        )
        return [dict(row) for row in rows]

async def search_open_food_facts(barcode: str):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            data = await response.json()
            if data.get("status") == 1:
                product = data["product"]
                return {
                    "name": product.get("product_name", "").strip(),
                    "brand": product.get("brands", "").strip(),
                }
    return None