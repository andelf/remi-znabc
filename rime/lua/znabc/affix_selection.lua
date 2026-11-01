local selection = {}

function selection.apply(context)
  if not context:get_option("znabc_selecting") or not context:has_menu() then return end
  local segment = context.composition:back()
  local expected = context:get_property("znabc_affix_input")
  local start = tonumber(context:get_property("znabc_affix_start"))
  local index = tonumber(context:get_property("znabc_affix_index"))
  if index and segment and start == segment.start and expected == context.input then
    context:highlight(index)
  end
end

return selection
