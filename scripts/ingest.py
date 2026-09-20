from investment_engine.infrastructure.db.session import session_scope
from investment_engine.data.ingestion.pipeline import MarketIngestionPipeline


def main():
    with session_scope() as session:
        results = MarketIngestionPipeline(session).run_full()
        for name, result in results.items():
            print(name, result)


if __name__ == "__main__":
    main()
