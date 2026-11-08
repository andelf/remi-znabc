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
  const char* comment = context.menu.num_candidates ? context.menu.candidates[0].comment : nullptr;
  std::string result = comment ? comment : "";
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

void check_continuous_input(RimeApi* api, RimeSessionId session) {
  api->set_option(session, "znabc_learning", False);
  auto expect = [&](const std::string& committed, const std::string& input) {
    auto actual = take_commit(api, session);
    require(actual == committed, "continuous input: expected commit [" + committed + "], got [" + actual + "]");
    require(std::string(api->get_input(session)) == input, "continuous input: unexpected raw input: " + input);
    require(candidates(api, session).empty(), "continuous input: menu remained open");
    require(!api->get_option(session, "znabc_selecting"), "continuous input: selection remained enabled");
    require(!api->get_option(session, "znabc_gbk"), "continuous input: GBK remained enabled");
  };
  for (const auto& example : std::vector<std::pair<std::string, std::string>>{
      {"zhongguo", "中国"}, {"zhongguoren", "中国人"}, {"zhongguodifang", "中国地方"},
      {"shijie]", "界"}, {"3235", "仂"}}) {
    type(api, session, example.first);
    open_menu(api, session);
    require(api->process_key(session, 'd', 0), "continuation key rejected");
    expect(example.second, "d");
  }
  type(api, session, "zhongguo");
  open_menu(api, session);
  for (unsigned char character : std::string("difang")) api->process_key(session, character, 0);
  expect("中国", "difang");
  open_menu(api, session);
  api->process_key(session, ' ', 0);
  expect("地方", "");

  type(api, session, "wenti");
  open_menu(api, session);
  require(api->highlight_candidate(session, 1), "cannot highlight 文体");
  api->process_key(session, 'd', 0);
  expect("文体", "d");
  type(api, session, "wenti");
  open_menu(api, session);
  select_text(api, session, "文");
  api->process_key(session, 'd', 0);
  expect("文体", "d");

  type(api, session, "shi");
  open_menu(api, session);
  api->process_key(session, 0xff56, 0);
  auto later_page = candidates(api, session);
  require(!later_page.empty(), "second page unavailable");
  api->process_key(session, 'd', 0);
  expect(later_page[0], "d");

  for (unsigned char character : std::string("iv")) {
    type(api, session, "zhongguo");
    open_menu(api, session);
    api->process_key(session, character, 0);
    expect("中国", std::string(1, character));
    for (unsigned char suffix : character == 'i' ? std::string("1") : std::string("love")) {
      api->process_key(session, suffix, 0);
    }
    api->process_key(session, ' ', 0);
    expect(character == 'i' ? "一" : "love", "");
  }
  for (const auto& input : {"ni32hao43", "hao43"}) {
    type(api, session, input);
    open_menu(api, session);
    api->process_key(session, 'd', 0);
    expect("", std::string(input) + "d");
  }
  type(api, session, "rong3414");
  api->process_key(session, 0xff0d, 0);
  require(api->get_option(session, "znabc_gbk") && !candidates(api, session).empty(),
      "GBK menu unavailable");
  api->process_key(session, 'd', 0);
  expect("", "rong3414d");
  type(api, session, "v1");
  open_menu(api, session);
  api->process_key(session, 'd', 0);
  expect("", "v1d");
  api->process_key(session, ' ', 0);
  expect("1d", "");
  type(api, session, "zhongguo");
  open_menu(api, session);
  api->process_key(session, 0xff1b, 0);
  api->process_key(session, 'd', 0);
  expect("", "zhongguod");
  type(api, session, "zhongguo");
  open_menu(api, session);
  api->set_caret_pos(session, 5);
  api->process_key(session, 'd', 0);
  expect("", "zhongdguo");
  type(api, session, "zhongguo");
  open_menu(api, session);
  api->process_key(session, '\'', 0);
  expect("", "zhongguo'");
  type(api, session, "zhongguo");
  open_menu(api, session);
  api->process_key(session, 0xff09, 0);
  require(api->get_option(session, "znabc_single_character"), "Tab mode not enabled");
  api->process_key(session, 'd', 0);
  expect("中过", "d");
  require(!api->get_option(session, "znabc_single_character"), "Tab mode leaked to next input");

  api->set_option(session, "znabc_learning", True);
  type(api, session, "ni32ni32hao43");
  open_menu(api, session);
  api->process_key(session, 'd', 0);
  expect("", "ni32ni32hao43d");
  type(api, session, "nini");
  open_menu(api, session);
  require(!contains(candidates(api, session), "你你"), "failed completion learned a partial word");
  type(api, session, "shijie");
  open_menu(api, session);
  auto source_comment = first_comment(api, session);
  for (const auto& example : std::vector<std::pair<std::string, std::string>>{
      {"shijie]", "界"}, {"3235", "仂"}}) {
    type(api, session, example.first);
    open_menu(api, session);
    api->process_key(session, 'd', 0);
    expect(example.second, "d");
  }
  type(api, session, "shijie");
  open_menu(api, session);
  require(first_comment(api, session) == source_comment, "extraction changed source usage");
  type(api, session, "zhongguo");
  open_menu(api, session);
  for (unsigned char character : std::string("difang")) api->process_key(session, character, 0);
  expect("中国", "difang");
  open_menu(api, session);
  api->process_key(session, ' ', 0);
  expect("地方", "");
  type(api, session, "zhongguodifang");
  open_menu(api, session);
  require(!contains(candidates(api, session), "中国地方"), "learned across separate inputs");
  api->process_key(session, 'd', 0);
  expect("中国地方", "d");
  type(api, session, "zhongguodifang");
  open_menu(api, session);
  require(contains(candidates(api, session), "中国地方"), "whole-input learning missing");
  type(api, session, "ni32ni32");
  open_menu(api, session);
  select_text(api, session, "倪");
  require(api->highlight_candidate(session, 1), "cannot highlight second 倪");
  api->process_key(session, 'd', 0);
  expect("倪倪", "d");
  type(api, session, "nini");
  open_menu(api, session);
  require(contains(candidates(api, session), "倪倪") && first_comment(api, session) == "〔新词 0/3〕",
      "continuous input learning missing or counted more than once");
}

int main(int count, char** arguments) {
  try {
    require(count == 3 || count == 4,
        "usage: rime_smoke USER_DIR LUA_PLUGIN [--learning-reload|--continuous-input]");
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
    if (count == 4 && std::string(arguments[3]) == "--continuous-input") {
      check_continuous_input(api, session);
      api->destroy_session(session);
      api->finalize();
      std::cout << "Rime continuous input checks passed\n";
      return EXIT_SUCCESS;
    }
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
      type(api, session, "wenti");
      open_menu(api, session);
      require(contains(candidates(api, session), "雯梯"), "mixed-menu word did not survive restart");
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
    require(candidates(api, session)[0] == "界", "suffix did not update automatically opened menu");
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
    require(candidates(api, session).empty(), "invalid remainder unexpectedly has candidates");
    require(api->get_option(session, "znabc_selecting"), "partial selection did not preserve selection state");
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
    require(take_commit(api, session) == "你" && std::string(api->get_input(session)) == "h" &&
        candidates(api, session).empty(), "letter did not commit selection and start next input");
    api->process_key(session, 0xff1b, 0);
    require(std::string(api->get_input(session)).empty(), "Escape did not clear composition");
    type(api, session, "nihao");
    api->process_key(session, '.', 0);
    require(take_commit(api, session) == "你好。", "punctuation commit failed");
    for (const auto& example : std::vector<std::pair<std::string, std::string>>{
        {"i", "一"}, {"I1", "壹"}, {"i123", "一二三"}, {"I123", "壹贰叁"},
        {"i0", "○"}, {"I0", "零"}, {"i1b2s3", "一百二十三"},
        {"i2006n6y3sr", "二○○六年六月三十日"}, {"iqk", "千克"},
        {"i2*3", "二乘三"}, {"i1/2", "一除二"}, {"i-3", "减三"}, {"i$", "元"}}) {
      type(api, session, example.first);
      api->process_key(session, ' ', 0);
      require(take_commit(api, session) == example.second, "quantity conversion failed: " + example.first);
      require(std::string(api->get_input(session)).empty(), "quantity input not cleared");
    }
    type(api, session, "i1");
    api->process_key(session, 0xff08, 0);
    api->process_key(session, '2', 0);
    api->process_key(session, 0xff0d, 0);
    require(take_commit(api, session) == "二", "quantity Backspace/Enter failed");
    type(api, session, "i1");
    api->process_key(session, 0xff1b, 0);
    require(std::string(api->get_input(session)).empty(), "quantity Escape failed");
    api->process_key(session, 'I', 1);
    api->process_key(session, '1', 0);
    api->process_key(session, ' ', 0);
    require(take_commit(api, session) == "壹", "Shift+I quantity failed");
    type(api, session, "i12.5");
    api->process_key(session, ' ', 0);
    require(take_commit(api, session).empty() && std::string(api->get_input(session)) == "i12.5", "invalid decimal silently changed value");
    api->process_key(session, 0xff1b, 0);
    for (const auto& input : {"enter", "hello", "ni32ke18"}) {
      type(api, session, input);
      require(api->process_key(session, 0xff0d, 0), "raw Return rejected");
      require(take_commit(api, session) == input, "unmatched Return did not commit raw input");
      require(std::string(api->get_input(session)).empty() && !api->get_option(session, "znabc_gbk") &&
          !api->get_option(session, "znabc_selecting"), "unmatched Return left selection state");
    }
    api->clear_composition(session);
    require(!api->process_key(session, 0xff0d, 0), "empty Return swallowed application key");
    for (int zone = 1; zone <= 9; ++zone) {
      type(api, session, "v" + std::to_string(zone));
      open_menu(api, session);
      auto rows = candidates(api, session);
      require(!rows.empty(), "symbol menu empty");
      api->process_key(session, 0xff56, 0);
      auto next = candidates(api, session);
      require(!next.empty() && next[0] != rows[0], "symbol paging failed");
      api->process_key(session, '2', 0);
      require(take_commit(api, session) == next[1], "symbol number selection failed");
      type(api, session, "v" + std::to_string(zone));
      api->process_key(session, 0xff0d, 0);
      rows = candidates(api, session);
      require(!rows.empty() && take_commit(api, session).empty(), "symbol Return did not open menu");
      api->process_key(session, 0xff0d, 0);
      require(take_commit(api, session) == rows[0], "symbol Return did not confirm candidate");
    }
    for (const auto& input : {"rong3414", "ro34", "r34144"}) {
      type(api, session, input);
      api->process_key(session, 0xff0d, 0);
      require(take_commit(api, session).empty(), "GBK Enter committed code");
      select_text(api, session, "鎔");
      require(take_commit(api, session) == "鎔", "GBK character selection failed");
    }
    type(api, session, "rong3414");
    open_menu(api, session);
    require(!contains(candidates(api, session), "鎔"), "ordinary lookup used full extension shape");
    for (const auto& input : {"pan335734", "335734"}) {
      type(api, session, input);
      api->process_key(session, 0xff0d, 0);
      select_text(api, session, "槃");
      require(take_commit(api, session) == "槃", "GBK full shape lookup failed");
    }
    for (int confirm : {32, 0xff0d}) {
      type(api, session, "rong3414");
      api->process_key(session, 0xff0d, 0);
      auto rows = candidates(api, session);
      require(!rows.empty(), "GBK confirmation needs a candidate");
      require(api->process_key(session, confirm, 0), "GBK confirmation leaked key to application");
      require(take_commit(api, session) == rows[0], "GBK confirmation failed");
    }
    type(api, session, "ni32pan335734");
    open_menu(api, session);
    select_text(api, session, "你");
    api->process_key(session, 0xff0d, 0);
    api->process_key(session, 0xff08, 0);
    require(!api->get_option(session, "znabc_gbk") && contains(candidates(api, session), "你"), "undo in GBK failed to reopen previous ordinary group");
    select_text(api, session, "你");
    api->process_key(session, 0xff0d, 0);
    select_text(api, session, "槃");
    require(take_commit(api, session) == "你槃", "GBK lookup after partial selection failed");
    require(!api->get_option(session, "znabc_gbk"), "GBK mode leaked after commit");
    type(api, session, "shi");
    api->process_key(session, 0xff0d, 0);
    auto gbk_first = candidates(api, session);
    api->process_key(session, ']', 0);
    require(candidates(api, session)[0] != gbk_first[0], "GBK next bracket page failed");
    api->process_key(session, '[', 0);
    require(candidates(api, session)[0] == gbk_first[0], "GBK previous bracket page failed");
    api->process_key(session, 0xff1b, 0);
    require(!api->get_option(session, "znabc_gbk") && candidates(api, session).empty(), "GBK Escape failed");
    open_menu(api, session);
    require(candidates(api, session)[0] == first_page[0], "GBK mode leaked into ordinary lookup");
    for (const auto& input : {"vlove", "vhello", "vabc09", "vv", "v", "vlove[", "vlove]", "v12", "v0", "v123", "v1abc"}) {
      type(api, session, input);
      api->process_key(session, ' ', 0);
      auto text = std::string(input).substr(1);
      require(take_commit(api, session) == (text.empty() ? "v" : text), "v literal commit differs: " + std::string(input));
      require(std::string(api->get_input(session)).empty(), "v literal input not cleared");
      require(!api->get_option(session, "ascii_mode"), "v literal changed language mode");
    }
    for (const auto& input : {"venter", "vLove", "vabc09", "vv", "v", "vlove[", "v12", "v0", "v123", "v1abc"}) {
      type(api, session, input);
      api->process_key(session, 0xff0d, 0);
      auto text = std::string(input).substr(1);
      require(take_commit(api, session) == (text.empty() ? "v" : text), "v literal Return differs: " + std::string(input));
      require(std::string(api->get_input(session)).empty() && !api->get_option(session, "ascii_mode"), "v Return did not reset input");
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
    require(take_commit(api, session).empty() && contains(candidates(api, session), "倪"), "partial numeric selection did not open next menu");
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
    require(take_commit(api, session) == "ni32ke18", "unmatched Return with ordinary menu did not commit raw input");
    type(api, session, "ni32ke18");
    open_menu(api, session);
    require(!contains(candidates(api, session), "倪可"), "raw Return learned a word");
    api->set_option(session, "znabc_learning", False);
    type(api, session, "ni32ke18");
    open_menu(api, session);
    api->process_key(session, '2', 0);
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
    api->process_key(session, '1', 0);
    require(take_commit(api, session) == "倪可", "second new word composition failed");
    type(api, session, "ni32ke18");
    open_menu(api, session);
    require(candidates(api, session)[0] == "倪可", "second new word not learned");
    require(api->process_key(session, 0xffff, 4), "Ctrl+Delete rejected");
    require(!contains(candidates(api, session), "倪可"), "user word deletion failed");
    api->process_key(session, '2', 0);
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
    require(take_commit(api, session).empty() && contains(candidates(api, session), "刻"), "fu selection did not open ke candidates");
    require(api->get_option(session, "znabc_single_character"), "character selection did not persist for remainder");
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
    type(api, session, "wenti");
    open_menu(api, session);
    auto mixed = candidates(api, session);
    require(mixed.size() >= 6 && mixed[0] == "问题" && mixed[1] == "文体" &&
        mixed[2] == "问" && mixed[3] == "文" && mixed[5] == "稳", "phrase-first mixed candidates differ");
    select_text(api, session, "雯");
    require(take_commit(api, session).empty() && !candidates(api, session).empty(), "mixed character did not open next menu");
    require(!api->get_option(session, "znabc_single_character"), "mixed menu unexpectedly enabled Tab mode");
    require(candidates(api, session)[0] == "提", "mixed character did not leave ti for conversion");
    select_text(api, session, "梯");
    require(take_commit(api, session) == "雯梯", "mixed characters consumed wrong input span");
    type(api, session, "wenti");
    open_menu(api, session);
    require(candidates(api, session)[0] == "雯梯" && first_comment(api, session) == "〔新词 0/3〕", "mixed characters were not learned");
    select_text(api, session, "文体");
    require(take_commit(api, session) == "文体", "mixed menu changed full-word commit");
    api->set_option(session, "znabc_learning", False);
    type(api, session, "wenti");
    open_menu(api, session);
    select_text(api, session, "文");
    require(candidates(api, session)[0] == "提", "next segment did not reset candidate page");
    api->process_key(session, ' ', 0);
    require(take_commit(api, session) == "文体", "space did not confirm the preselected suffix immediately");
    type(api, session, "wenti");
    open_menu(api, session);
    select_text(api, session, "文");
    auto before_escape = std::string(api->get_input(session));
    api->process_key(session, 0xff1b, 0);
    require(candidates(api, session).empty() && std::string(api->get_input(session)) == before_escape &&
        !api->get_option(session, "znabc_selecting"), "Escape did not close automatically opened menu");
    api->process_key(session, '3', 0);
    require(std::string(api->get_input(session)) == before_escape + "3" &&
        candidates(api, session).empty() && take_commit(api, session).empty(), "numeric shape editing after Escape failed");
    open_menu(api, session);
    require(!candidates(api, session).empty(), "edited remainder cannot reopen menu");
    type(api, session, "wenti");
    open_menu(api, session);
    select_text(api, session, "文");
    auto before_backspace = std::string(api->get_input(session));
    api->process_key(session, 0xff08, 0);
    require(std::string(api->get_input(session)) == before_backspace &&
        contains(candidates(api, session), "文体") && take_commit(api, session).empty() &&
        api->get_option(session, "znabc_selecting"), "Backspace did not reopen previous selection without deleting code");
    select_text(api, session, "问");
    select_text(api, session, "提");
    require(take_commit(api, session) == "问提", "reselected character did not replace previous selection");
    type(api, session, "zhongguoren");
    open_menu(api, session);
    select_text(api, session, "中国");
    api->process_key(session, 0xff08, 0);
    require(std::string(api->get_input(session)) == "zhongguoren" && contains(candidates(api, session), "中国") &&
        take_commit(api, session).empty(), "Backspace did not undo whole selected phrase");
    select_text(api, session, "中国");
    select_text(api, session, "人");
    require(take_commit(api, session) == "中国人", "phrase reselection lost remaining input");
    type(api, session, "wenzhongguoren");
    open_menu(api, session);
    select_text(api, session, "文");
    select_text(api, session, "中国");
    api->process_key(session, 0xff08, 0);
    require(std::string(api->get_input(session)) == "wenzhongguoren" && contains(candidates(api, session), "中国"),
        "first Backspace did not undo last selected group");
    api->process_key(session, 0xff08, 0);
    require(std::string(api->get_input(session)) == "wenzhongguoren" && contains(candidates(api, session), "文"),
        "second Backspace did not undo earlier selected group");
    api->process_key(session, 0xff08, 0);
    require(std::string(api->get_input(session)) == "wenzhongguore" && candidates(api, session).empty(),
        "Backspace without previous selection did not resume code editing");
    type(api, session, "ni32hao43");
    open_menu(api, session);
    select_text(api, session, "你");
    api->process_key(session, 0xff08, 0);
    require(std::string(api->get_input(session)) == "ni32hao43" && contains(candidates(api, session), "你"),
        "Backspace with empty remainder menu lost shape codes");
    type(api, session, "fuke");
    open_menu(api, session);
    api->process_key(session, 0xff09, 0);
    select_text(api, session, "复");
    api->process_key(session, 0xff08, 0);
    require(std::string(api->get_input(session)) == "fuke" && !candidates(api, session).empty() &&
        api->get_option(session, "znabc_single_character"), "Backspace lost character-only mode");
    select_text(api, session, "复");
    select_text(api, session, "刻");
    require(take_commit(api, session) == "复刻", "character-only reselection failed");
    type(api, session, "wenshijie");
    open_menu(api, session);
    select_text(api, session, "文");
    require(candidates(api, session)[0] == "世界", "next segment lost phrase matching");
    select_text(api, session, "世界");
    require(take_commit(api, session) == "文世界", "remaining phrase commit failed");
    type(api, session, "zhongguoren");
    open_menu(api, session);
    select_text(api, session, "中国");
    require(contains(candidates(api, session), "人") && take_commit(api, session).empty(), "partial phrase did not open next menu");
    select_text(api, session, "人");
    require(take_commit(api, session) == "中国人", "partial phrase continuation failed");
    api->set_option(session, "znabc_user_dict", False);
    type(api, session, "ni32ni32");
    open_menu(api, session);
    api->process_key(session, '2', 4);
    require(contains(candidates(api, session), "倪") && take_commit(api, session).empty(), "Ctrl+number did not open next menu");
    api->process_key(session, '2', 4);
    require(take_commit(api, session) == "倪倪", "consecutive Ctrl+number selection failed");
    api->set_option(session, "znabc_user_dict", True);
    api->set_option(session, "znabc_learning", True);
    type(api, session, "ni32ni32hao63");
    open_menu(api, session);
    select_text(api, session, "倪");
    select_text(api, session, "倪");
    api->process_key(session, 0xff08, 0);
    select_text(api, session, "你");
    select_text(api, session, "好");
    require(take_commit(api, session) == "倪你好", "undo/reselection changed committed text");
    type(api, session, "ni32ni32hao63");
    open_menu(api, session);
    require(contains(candidates(api, session), "倪你好") && !contains(candidates(api, session), "倪倪好"),
        "learning retained an undone selection");
    api->clear_composition(session);
    for (const auto& bracket : {'[', ']'}) {
      auto handled = api->process_key(session, bracket, 0);
      auto committed = take_commit(api, session);
      require(std::string(api->get_input(session)).empty() &&
          (handled ? committed == std::string(1, bracket) : committed.empty()), "standalone bracket was treated as suffix");
    }
    api->set_option(session, "znabc_learning", False);
    api->set_option(session, "znabc_user_dict", False);
    type(api, session, "jiuni32hao63");
    open_menu(api, session);
    require(candidates(api, session)[0] == "就", "prefix changed candidate order");
    api->process_key(session, ' ', 0);
    select_text(api, session, "你好");
    require(take_commit(api, session) == "旧你好", "prefix was not preselected");
    type(api, session, "jiuni32hao63");
    open_menu(api, session);
    select_text(api, session, "就");
    select_text(api, session, "你好");
    require(take_commit(api, session) == "就你好", "prefix blocked manual selection");
    type(api, session, "wulixi");
    open_menu(api, session);
    select_text(api, session, "物理");
    require(candidates(api, session)[0] == "西", "suffix changed candidate order");
    api->process_key(session, ' ', 0);
    require(take_commit(api, session) == "物理系", "suffix was not preselected");
    type(api, session, "wulixi");
    open_menu(api, session);
    select_text(api, session, "物理");
    select_text(api, session, "西");
    require(take_commit(api, session) == "物理西", "suffix blocked manual selection");
    type(api, session, "wulixi");
    open_menu(api, session);
    select_text(api, session, "物理");
    api->process_key(session, 0xff08, 0);
    select_text(api, session, "武力");
    api->process_key(session, ' ', 0);
    require(take_commit(api, session) == "武力系", "suffix undo/reselection failed");
    type(api, session, "wulixi");
    open_menu(api, session);
    select_text(api, session, "物理");
    api->process_key(session, 0xff09, 0);
    api->process_key(session, ' ', 0);
    require(take_commit(api, session) == "物理西", "Tab did not disable suffix preselection");
    type(api, session, "wulixi");
    open_menu(api, session);
    select_text(api, session, "物理");
    api->process_key(session, 0xff09, 0);
    api->process_key(session, 0xff09, 0);
    api->process_key(session, ' ', 0);
    require(take_commit(api, session) == "物理系", "leaving Tab mode did not restore suffix preselection");
    api->set_option(session, "znabc_user_dict", True);
    api->set_option(session, "znabc_learning", True);
    type(api, session, "wulixi");
    open_menu(api, session);
    select_text(api, session, "物理");
    api->process_key(session, ' ', 0);
    require(take_commit(api, session) == "物理系", "learning changed suffix commit");
    type(api, session, "wulixi");
    open_menu(api, session);
    require(candidates(api, session)[0] == "物理系", "confirmed suffix combination was not learned");
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
