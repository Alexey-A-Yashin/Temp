#!/bin/sh
# Согласованность вызовов между слоями, которые пробник не собирает целиком.
#
# Пробник godotcheck собирает ЗАГЛУШКИ вместо LevelView3D и GameBootstrap: они на
# тысячи строк и завязаны на Godot. Поэтому ошибки вида «у такого-то нет такого
# метода» проходят насквозь — так было дважды:
#
#   V241  LevelView3D звал FarBackground.SetWaterVisible, которого не было
#   V274  GameBootstrap звал LevelView3D.SetStemMarkersVisible, который я удалил
#
# Здесь без всякой сборки сверяется: всё, что один слой зовёт у другого, должно
# быть в нём объявлено.
P="$1/scripts"

# методы самого Godot — объявлять их не надо
GODOT="GetChildCount|GetChild|AddChild|QueueFree|GetParent|Visible|Name|GlobalPosition|Position|Free|IsInsideTree|CallDeferred|SetProcess|GetTree|GetViewport"

check() {
  caller="$1"; callee="$2"; var="$3"
  [ -f "$caller" ] || return
  [ -f "$callee" ] || return
  echo "  $(basename "$caller") -> $(basename "$callee"):"
  grep -o "$var[?]*\.[A-Za-z_][A-Za-z0-9_]*" "$caller" 2>/dev/null \
    | sed 's/.*\.//' | sort -u | while read m; do
      echo "$m" | grep -qE "^($GODOT)$" && continue
      grep -q "public .*[ .]$m(\|public .* $m *{\|public .* $m;\|public .* $m *=>" "$callee" \
        || echo "    ОТСУТСТВУЕТ: $m"
    done
}

echo "Проверка согласованности вызовов:"
check "$P/Presentation/Level/LevelView3D.cs"  "$P/Presentation/Level/FarBackground.cs" "_farBackground"
check "$P/Bootstrap/GameBootstrap.cs"         "$P/Presentation/Level/LevelView3D.cs"   "_view"
check "$P/Bootstrap/GameBootstrap.cs"         "$P/Presentation/Level/FarBackground.cs" "FarBackground"
echo "готово"
