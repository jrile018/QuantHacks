add_executable(gm-backtest-tests
  deflated_sharpe_test.cpp
  trade_simulation_test.cpp
  sample_moments_test.cpp
)

target_link_libraries(gm-backtest-tests
  PRIVATE
    gm::backtest
    Catch2::Catch2WithMain
)

catch_discover_tests(gm-backtest-tests)
