#include <rime_api.h>
#include <dlfcn.h>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

void require(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

std::vector<std::string> candidates(RimeApi* api, RimeSessionId session) {
  RimeContext context{};
  RIME_STRUCT_INIT(RimeContext, context);
  require(api->get_context(session, &context), "get_context failed");
  std::vector<std::string> result;
  for (int index = 0; index < context.menu.num_candidates; ++index) {
    result.emplace_back(context.menu.candidates[index].text);
  }
  api->free_context(&context);
  return result;
}

bool contains(const std::vector<std::string>& values, const std::string& text) {
  for (const auto& value : values) {
    if (value == text) {
      return true;
    }
  }
  return false;
}

void type(RimeApi* api, RimeSessionId session, const std::string& input) {
  api->clear_composition(session);
  for (unsigned char character : input) {
    require(api->process_key(session, character, 0), "key rejected: " + input);
  }
  require(std::string(api->get_input(session)) == input, "raw input changed: " + input);
  require(candidates(api, session).empty(), "menu visible before space: " + input);
}

std::string take_commit(RimeApi* api, RimeSessionId session) {
  RimeCommit commit{};
  RIME_STRUCT_INIT(RimeCommit, commit);
  if (!api->get_commit(session, &commit)) {
    return "";
  }
  std::string text(commit.text);
  api->free_commit(&commit);
  return text;
}

void open_menu(RimeApi* api, RimeSessionId session) {
  auto input = std::string(api->get_input(session));
  require(api->process_key(session, ' ', 0), "opening space rejected");
  require(take_commit(api, session).empty(), "opening space committed text");
  require(std::string(api->get_input(session)) == input, "opening space changed input");
}

int main(int count, char** arguments) {
  try {
    require(count == 3, "usage: rime_smoke USER_DIR LUA_PLUGIN");
    void* plugin = dlopen(arguments[2], RTLD_NOW | RTLD_GLOBAL);
    require(plugin != nullptr, "cannot load Lua plugin");
    RimeApi* api = rime_get_api();
    RimeTraits traits{};
    RIME_STRUCT_INIT(RimeTraits, traits);
    const char* modules[] = {"default", "lua", nullptr};
    traits.shared_data_dir = arguments[1];
    traits.user_data_dir = arguments[1];
    traits.app_name = "rime.znabc_smoke";
    traits.modules = modules;
    traits.min_log_level = 2;
    traits.log_dir = "";
    api->setup(&traits);
    api->initialize(&traits);
    if (api->start_maintenance(True)) {
      api->join_maintenance_thread();
    }
    auto session = api->create_session();
    require(session != 0, "create_session failed");
    require(api->select_schema(session, "znabc"), "select_schema failed");
    for (const auto& input : {"nihao", "ni32hao63", "ni3hao6"}) {
      type(api, session, input);
      open_menu(api, session);
      require(contains(candidates(api, session), "你好"), std::string("missing 你好: ") + input);
      api->process_key(session, ' ', 0);
      require(take_commit(api, session) == "你好", "space commit differs");
    }
    type(api, session, "shi81");
    open_menu(api, session);
    auto expected = candidates(api, session);
    require(contains(expected, "时") && contains(expected, "是") && contains(expected, "匙"), "shape candidates differ");
    require(expected.size() >= 2, "missing second candidate");
    api->process_key(session, '2', 0);
    require(take_commit(api, session) == expected[1], "2 did not commit second candidate");
    type(api, session, "shi");
    open_menu(api, session);
    auto first_page = candidates(api, session);
    require(api->process_key(session, 0xff56, 0), "PageDown rejected");
    expected = candidates(api, session);
    require(expected.size() >= 2 && expected[0] != first_page[0], "PageDown did not change candidates");
    api->process_key(session, '2', 0);
    require(take_commit(api, session) == expected[1], "2 selected from wrong page");
    type(api, session, "3235");
    open_menu(api, session);
    expected = candidates(api, session);
    require(expected.size() == 3 && expected[0] == "仂" && expected[1] == "你" && expected[2] == "仍", "shape order differs");
    api->process_key(session, '2', 0);
    require(take_commit(api, session) == "你", "pure shape numeric selection failed");
    type(api, session, "ni32");
    open_menu(api, session);
    api->process_key(session, '2', 0);
    require(take_commit(api, session) == "倪", "ni32 space 2 did not commit 倪");
    for (unsigned char character : std::string("ni32")) {
      require(api->process_key(session, character, 0), "fresh input after selection rejected");
    }
    require(std::string(api->get_input(session)) == "ni32" && candidates(api, session).empty(), "selection state leaked into next input");
    open_menu(api, session);
    api->process_key(session, '2', 4);
    require(take_commit(api, session) == "倪", "Ctrl+2 compatibility failed");
    type(api, session, "ni32hao43");
    open_menu(api, session);
    expected = candidates(api, session);
    require(!contains(expected, "你好") && !expected.empty(), "shape rejection/fallback failed");
    api->process_key(session, ' ', 0);
    require(std::string(api->get_input(session)).find("hao43") != std::string::npos, "partial selection lost remaining input");
    require(candidates(api, session).empty(), "partial selection did not return to editing");
    open_menu(api, session);
    require(api->get_option(session, "znabc_selecting"), "remaining input cannot enter selection");
    api->process_key(session, ' ', 0);
    require(take_commit(api, session).empty(), "empty menu committed raw code");
    type(api, session, "ke18");
    open_menu(api, session);
    require(contains(candidates(api, session), "可"), "summary metadata not applied");
    type(api, session, "ke15");
    open_menu(api, session);
    require(!contains(candidates(api, session), "可"), "full-shape prefix used as summary");
    type(api, session, "ni32");
    open_menu(api, session);
    api->process_key(session, '9', 0);
    require(take_commit(api, session).empty(), "invalid candidate key committed text");
    require(std::string(api->get_input(session)) == "ni32", "invalid candidate key edited code");
    api->process_key(session, 0xff1b, 0);
    require(candidates(api, session).empty() && std::string(api->get_input(session)) == "ni32", "Escape did not return to editing");
    api->process_key(session, '3', 0);
    require(std::string(api->get_input(session)) == "ni323", "digit after Escape did not edit");
    open_menu(api, session);
    api->process_key(session, 0xff08, 0);
    require(std::string(api->get_input(session)) == "ni32", "Backspace did not edit suffix");
    require(candidates(api, session).empty(), "Backspace did not close menu");
    open_menu(api, session);
    api->process_key(session, 'h', 0);
    require(std::string(api->get_input(session)) == "ni32h" && candidates(api, session).empty(), "letter did not resume editing");
    api->process_key(session, 0xff1b, 0);
    require(std::string(api->get_input(session)).empty(), "Escape did not clear composition");
    type(api, session, "nihao");
    api->process_key(session, '.', 0);
    require(take_commit(api, session) == "你好。", "punctuation commit failed");
    for (const auto& input : {"vlove", "vhello", "vabc09", "vv", "v"}) {
      type(api, session, input);
      api->process_key(session, ' ', 0);
      auto text = std::string(input).substr(1);
      require(take_commit(api, session) == (text.empty() ? "v" : text), "v literal commit differs: " + std::string(input));
      require(std::string(api->get_input(session)).empty(), "v literal input not cleared");
      require(!api->get_option(session, "ascii_mode"), "v literal changed language mode");
    }
    type(api, session, "vLove");
    require(api->process_key(session, 'R', 1), "shifted English letter rejected");
    api->process_key(session, ' ', 0);
    require(take_commit(api, session) == "LoveR", "v literal did not preserve case");
    type(api, session, "vlove");
    api->process_key(session, 0xff08, 0);
    api->process_key(session, ' ', 0);
    require(take_commit(api, session) == "lov", "v literal Backspace failed");
    type(api, session, "vlove");
    api->process_key(session, 0xff1b, 0);
    require(std::string(api->get_input(session)).empty() && take_commit(api, session).empty(), "v literal Escape did not cancel");
    type(api, session, "ni32");
    open_menu(api, session);
    api->process_key(session, '2', 0);
    require(take_commit(api, session) == "倪", "Chinese selection after v literal failed");
    api->clear_composition(session);
    api->set_option(session, "ascii_mode", True);
    require(!api->process_key(session, '3', 0), "ASCII mode intercepted numeric key");
    api->destroy_session(session);
    api->finalize();
    std::cout << "Rime integration checks passed\n";
    return EXIT_SUCCESS;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return EXIT_FAILURE;
  }
}
