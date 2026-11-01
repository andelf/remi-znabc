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

std::string first_comment(RimeApi* api, RimeSessionId session) {
  RimeContext context{};
  RIME_STRUCT_INIT(RimeContext, context);
  require(api->get_context(session, &context), "get_context failed");
  std::string result = context.menu.num_candidates ? context.menu.candidates[0].comment : "";
  api->free_context(&context);
  return result;
}

void open_menu(RimeApi* api, RimeSessionId session) {
  auto input = std::string(api->get_input(session));
  require(api->process_key(session, ' ', 0), "opening space rejected");
  require(take_commit(api, session).empty(), "opening space committed text");
  require(std::string(api->get_input(session)) == input, "opening space changed input");
}

void select_text(RimeApi* api, RimeSessionId session, const std::string& text) {
  for (int page = 0; page < 20; ++page) {
    auto rows = candidates(api, session);
    for (size_t index = 0; index < rows.size(); ++index) {
      if (rows[index] == text) {
        require(api->process_key(session, '1' + index, 0), "candidate number rejected");
        return;
      }
    }
    require(api->process_key(session, 0xff56, 0), "candidate page rejected");
  }
  throw std::runtime_error("candidate missing: " + text);
}

int main(int count, char** arguments) {
  try {
    require(count == 3 || count == 4, "usage: rime_smoke USER_DIR LUA_PLUGIN [--learning-reload]");
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
    if (count == 4) {
      require(std::string(arguments[3]) == "--learning-reload", "unknown argument");
      type(api, session, "ni32ni32");
      open_menu(api, session);
      require(candidates(api, session)[0] == "倪倪" && first_comment(api, session) == "〔常用〕", "learned word did not survive process restart");
      type(api, session, "ni32ke18");
      open_menu(api, session);
      require(!contains(candidates(api, session), "倪可"), "deletion did not survive process restart");
      type(api, session, "fuke");
      open_menu(api, session);
      require(contains(candidates(api, session), "复刻"), "manually segmented word did not survive restart");
      api->destroy_session(session);
      api->finalize();
      std::cout << "Rime learning restart checks passed\n";
      return EXIT_SUCCESS;
    }
    for (const auto& input : {"nihao", "ni32hao63", "ni3hao6"}) {
      type(api, session, input);
      open_menu(api, session);
      require(contains(candidates(api, session), "你好"), std::string("missing 你好: ") + input);
      api->process_key(session, ' ', 0);
      require(take_commit(api, session) == "你好", "space commit differs");
    }
    for (const auto& input : {"shijie[", "shijie]"}) {
      type(api, session, input);
      open_menu(api, session);
      auto character = std::string(input).back() == '[' ? "世" : "界";
      require(candidates(api, session)[0] == character && first_comment(api, session) == " 世界", "word character candidates differ");
      api->process_key(session, ' ', 0);
      require(take_commit(api, session) == character && std::string(api->get_input(session)).empty(), "word character did not consume full code");
    }
    type(api, session, "fuke]");
    open_menu(api, session);
    require(candidates(api, session).size() == 2, "word character choices lost");
    api->process_key(session, '2', 0);
    require(take_commit(api, session) == "科", "numeric word character selection failed");
    type(api, session, "fuke");
    open_menu(api, session);
    require(candidates(api, session)[0] == "复课", "word character selection learned its source word");
    type(api, session, "shijie");
    open_menu(api, session);
    require(api->process_key(session, ']', 0), "suffix after opening menu rejected");
    require(std::string(api->get_input(session)) == "shijie]" && candidates(api, session)[0] == "界", "suffix after opening menu failed");
    api->process_key(session, '[', 0);
    require(std::string(api->get_input(session)) == "shijie[" && candidates(api, session)[0] == "世", "suffix replacement failed");
    api->process_key(session, 0xff08, 0);
    require(std::string(api->get_input(session)) == "shijie" && candidates(api, session).empty(), "suffix Backspace failed");
    open_menu(api, session);
    require(candidates(api, session)[0] == "世界", "removing suffix did not restore phrases");
    type(api, session, "shi[");
    open_menu(api, session);
    require(candidates(api, session).empty(), "single syllable incorrectly accepted word suffix");
    api->process_key(session, ' ', 0);
    require(take_commit(api, session).empty(), "invalid word suffix committed raw code");
    api->process_key(session, 0xff08, 0);
    require(std::string(api->get_input(session)) == "shi", "invalid suffix cannot be removed");
    type(api, session, "ni32shijie");
    open_menu(api, session);
    select_text(api, session, "你");
    require(take_commit(api, session).empty(), "prefix before word character committed early");
    api->process_key(session, ']', 0);
    open_menu(api, session);
    select_text(api, session, "界");
    require(take_commit(api, session) == "你界", "word character after selected prefix failed");
    type(api, session, "ni32jie");
    open_menu(api, session);
    require(!contains(candidates(api, session), "你界"), "word character polluted automatic word learning");
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
    for (const auto& input : {"vlove", "vhello", "vabc09", "vv", "v", "vlove[", "vlove]"}) {
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
    type(api, session, "ni32ni32");
    open_menu(api, session);
    require(!contains(candidates(api, session), "倪倪"), "learning test needs a fresh user directory");
    api->process_key(session, '2', 0);
    require(take_commit(api, session).empty() && candidates(api, session).empty(), "partial numeric selection committed early or opened next menu");
    open_menu(api, session);
    api->process_key(session, '2', 0);
    require(take_commit(api, session) == "倪倪", "new word composition failed");
    for (int uses = 0; uses < 3; ++uses) {
      type(api, session, "ni32ni32");
      open_menu(api, session);
      require(candidates(api, session)[0] == "倪倪", "new word not recalled");
      require(first_comment(api, session) == "〔新词 " + std::to_string(uses) + "/3〕", "temporary usage count differs");
      api->process_key(session, '1', 0);
      require(take_commit(api, session) == "倪倪", "new word reuse failed");
    }
    type(api, session, "nn");
    open_menu(api, session);
    require(candidates(api, session)[0] == "倪倪" && first_comment(api, session) == "〔常用〕", "promotion or abbreviation lookup failed");
    type(api, session, "ni63ni32");
    open_menu(api, session);
    require(!contains(candidates(api, session), "倪倪"), "user word ignored shape filtering");
    api->set_option(session, "znabc_user_dict", False);
    type(api, session, "ni32ni32");
    open_menu(api, session);
    require(!contains(candidates(api, session), "倪倪"), "user dictionary disable failed");
    api->set_option(session, "znabc_user_dict", True);
    type(api, session, "ni32");
    open_menu(api, session);
    api->process_key(session, '2', 0);
    require(take_commit(api, session) == "倪", "independent first commit failed");
    type(api, session, "ke18");
    open_menu(api, session);
    api->process_key(session, '1', 0);
    require(take_commit(api, session) == "可", "independent second commit failed");
    type(api, session, "ni32ke18");
    open_menu(api, session);
    require(!contains(candidates(api, session), "倪可"), "independent commits were merged");
    api->process_key(session, '2', 0);
    auto other_session = api->create_session();
    require(other_session != 0 && api->select_schema(other_session, "znabc"), "second session failed");
    type(api, other_session, "nn");
    open_menu(api, other_session);
    require(candidates(api, other_session)[0] == "倪倪", "second session cannot share dictionary");
    type(api, other_session, "ke18");
    open_menu(api, other_session);
    api->process_key(other_session, '1', 0);
    require(take_commit(api, other_session) == "可", "second session commit failed");
    api->destroy_session(other_session);
    api->clear_composition(session);
    type(api, session, "ni32ke18");
    open_menu(api, session);
    require(!contains(candidates(api, session), "倪可"), "sessions shared composition history");
    api->process_key(session, 0xff0d, 0);
    require(take_commit(api, session) == "ni32ke18", "raw Return changed input");
    type(api, session, "ni32ke18");
    open_menu(api, session);
    require(!contains(candidates(api, session), "倪可"), "raw Return learned a word");
    api->set_option(session, "znabc_learning", False);
    type(api, session, "ni32ke18");
    open_menu(api, session);
    api->process_key(session, '2', 0);
    open_menu(api, session);
    api->process_key(session, '1', 0);
    require(take_commit(api, session) == "倪可", "frozen composition failed");
    type(api, session, "ni32ke18");
    open_menu(api, session);
    require(!contains(candidates(api, session), "倪可"), "frozen learning wrote a new word");
    api->set_option(session, "znabc_learning", True);
    api->process_key(session, '2', 0);
    api->clear_composition(session);
    type(api, session, "ni32ke18");
    open_menu(api, session);
    require(!contains(candidates(api, session), "倪可"), "cancelled composition was learned");
    api->process_key(session, '2', 0);
    open_menu(api, session);
    api->process_key(session, '1', 0);
    require(take_commit(api, session) == "倪可", "second new word composition failed");
    type(api, session, "ni32ke18");
    open_menu(api, session);
    require(candidates(api, session)[0] == "倪可", "second new word not learned");
    require(api->process_key(session, 0xffff, 4), "Ctrl+Delete rejected");
    require(!contains(candidates(api, session), "倪可"), "user word deletion failed");
    api->process_key(session, '2', 0);
    open_menu(api, session);
    api->process_key(session, '1', 0);
    require(take_commit(api, session) == "倪可", "deleted word reconstruction failed");
    type(api, session, "ni32ke18");
    open_menu(api, session);
    require(!contains(candidates(api, session), "倪可"), "deleted word was immediately learned again");
    type(api, session, "fuke");
    open_menu(api, session);
    require(contains(candidates(api, session), "复课") && contains(candidates(api, session), "妇科"), "fuke phrase candidates missing");
    require(api->process_key(session, 0xff09, 0), "Tab rejected");
    require(api->get_option(session, "znabc_single_character"), "Tab did not enter character selection");
    require(!contains(candidates(api, session), "复课") && contains(candidates(api, session), "副"), "Tab did not query fu characters");
    api->process_key(session, 0xff09, 0);
    require(contains(candidates(api, session), "复课"), "second Tab did not restore phrases");
    api->process_key(session, 0xff09, 0);
    select_text(api, session, "复");
    require(take_commit(api, session).empty() && candidates(api, session).empty(), "fu selection committed prematurely");
    require(api->get_option(session, "znabc_single_character"), "character selection did not persist for remainder");
    open_menu(api, session);
    select_text(api, session, "刻");
    require(take_commit(api, session) == "复刻", "manual character composition failed");
    require(!api->get_option(session, "znabc_single_character"), "character selection leaked into next composition");
    type(api, session, "fuke");
    open_menu(api, session);
    require(contains(candidates(api, session), "复刻"), "manual composition did not create a user word");
    type(api, session, "fuke[");
    open_menu(api, session);
    require(candidates(api, session).size() == 2 && first_comment(api, session) == " 复刻", "user word extraction or character deduplication failed");
    type(api, session, "fuke]");
    open_menu(api, session);
    require(candidates(api, session)[0] == "刻", "user word last character missing");
    api->process_key(session, 0xffff, 4);
    require(candidates(api, session)[0] == "刻", "deleting extracted character removed source word");
    select_text(api, session, "刻");
    require(take_commit(api, session) == "刻", "user word last character commit failed");
    type(api, session, "fuke");
    open_menu(api, session);
    require(first_comment(api, session) == "〔新词 0/3〕", "word character selection changed source usage counter");
    api->process_key(session, 0xff09, 0);
    api->process_key(session, 0xff1b, 0);
    api->process_key(session, 0xff1b, 0);
    require(!api->get_option(session, "znabc_single_character"), "cancelled composition retained character mode");
    api->clear_composition(session);
    for (const auto& bracket : {'[', ']'}) {
      auto handled = api->process_key(session, bracket, 0);
      auto committed = take_commit(api, session);
      require(std::string(api->get_input(session)).empty() &&
          (handled ? committed == std::string(1, bracket) : committed.empty()), "standalone bracket was treated as suffix");
    }
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
