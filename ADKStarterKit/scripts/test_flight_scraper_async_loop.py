import asyncio

from travel_concierge.tools.flights import search_flights_playwright


async def main() -> None:
    result = search_flights_playwright(
        origin="banglore",
        destination="kochi",
        departure_date="17th may",
        return_date="",
        max_results=3,
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
