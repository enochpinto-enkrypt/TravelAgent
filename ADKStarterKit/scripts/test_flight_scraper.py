from travel_concierge.tools.flights import search_flights_playwright

if __name__ == "__main__":
    result = search_flights_playwright(
        origin="Bangalore",
        destination="Kochi",
        departure_date="2024-05-17",
        return_date="",
        max_results=3,
    )
    print(result)
