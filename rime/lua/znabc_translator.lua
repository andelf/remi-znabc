local Engine = require("znabc.engine")
local parser = require("znabc.parser")
local translator = {}

function translator.init(env)
  local configured = env.engine.schema.config:get_string("znabc/data_dir")
  local directory = configured or (rime_api.get_user_data_dir() .. "/znabc_data")
  env.abc = Engine.new(directory)
end

function translator.func(input, segment, env)
  if not segment:has_tag("abc") or not env.engine.context:get_option("znabc_selecting") then
    return
  end
  local candidates, consumed, units, mode = env.abc:query(input)
  if consumed == 0 then
    return
  end
  local preedit = {}
  if mode == "shape" then
    preedit[1] = input
  else
    for _, unit in ipairs(units) do
      if unit.finish <= consumed then
        preedit[#preedit + 1] = input:sub(unit.start + 1, unit.finish)
      end
    end
  end
  for index, item in ipairs(candidates) do
    local comment = ""
    if item.packed then
      comment = " " .. parser.syllable(item.packed)
    end
    local candidate = Candidate("znabc", segment.start, segment.start + consumed, item.text, comment)
    candidate.preedit = table.concat(preedit, " ")
    candidate.quality = 1000 - index / 10000
    yield(candidate)
  end
end

function translator.fini(env)
  env.abc = nil
end

return translator

