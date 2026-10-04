gm_add_stage_app(gm-features)
target_sources(gm-features PRIVATE centrality.cpp returns.cpp valuation.cpp market_model.cpp)
target_link_libraries(gm-features PRIVATE gm::data gm::io)

if (GM_BUILD_TESTS)
  add_subdirectory(tests)
endif()
