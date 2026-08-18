#!/bin/sh
# ПРОВЕРКА ОБЪЯВЛЕНИЙ ПРОСТРАНСТВ ИМЁН в файлах, которые пробник НЕ СОБИРАЕТ.
#
# godotcheck подменяет LevelView3D и GameBootstrap заглушками — они на тысячи
# строк и завязаны на Godot. Поэтому ошибки ВНУТРИ них проходят насквозь, и за
# два дня это случилось трижды:
#
#   V275  GameBootstrap звал удалённый метод LevelView3D
#   V279  LevelView3D звал RingVegetationPlacer без using
#   V279  LevelView3D обращался к _target — полю ДРУГОГО класса
#
# Здесь сверяется: если файл упоминает наш тип, у него должно быть объявление
# нужного пространства имён (или полное имя типа).
P="$1/scripts"

# где какой тип объявлен: имя -> пространство имён
map=$(mktemp)
find "$P" -name "*.cs" | while read f; do
  ns=$(grep -m1 "^namespace " "$f" | sed 's/^namespace //; s/;.*//' | tr -d ' \r')
  [ -z "$ns" ] && continue
  grep -oE "^(public|internal) +(static +|sealed +|abstract +|partial +|readonly +)*(class|struct|record|enum|interface) +[A-Za-z_][A-Za-z0-9_]*" "$f" \
    | awk '{print $NF}' | while read t; do echo "$t $ns"; done
done | sort -u > "$map"

echo "Проверка объявлений пространств имён:"
for f in "$P/Presentation/Level/LevelView3D.cs" "$P/Bootstrap/GameBootstrap.cs" \
         "$P/Presentation/Level/FarBackground.cs"; do
  [ -f "$f" ] || continue
  own=$(grep -m1 "^namespace " "$f" | sed 's/^namespace //; s/;.*//' | tr -d ' \r')
  usings=$(grep "^using " "$f" | sed 's/^using //; s/;.*//' | tr -d ' \r')
  # типы, упомянутые в КОДЕ. Комментарии выброшены: в них полно упоминаний
  # чужих классов, и без этого проверка кричала бы зря.
  code=$(mktemp)
  # выбрасываем комментарии И содержимое строк: в них попадаются слова с большой
  # буквы, которые не являются типами.
  sed 's://.*::; s:"[^"]*":"":g' "$f" > "$code"
  grep -oE "\b[A-Z][A-Za-z0-9_]{2,}\b" "$code" | sort -u | while read t; do
    ns=$(awk -v T="$t" '$1==T {print $2; exit}' "$map")
    [ -z "$ns" ] && continue
    [ "$ns" = "$own" ] && continue
    # полное имя в файле — тоже годится
    grep -q "$ns\.$t" "$code" && continue
    echo "$usings" | grep -qx "$ns" || echo "  $(basename "$f"): $t из $ns — НЕТ using"
  done
  rm -f "$code"
done
rm -f "$map"

# ---- ХОДОВЫЕ ТИПЫ БИБЛИОТЕКИ ----
#
# Проверка выше сверяет только НАШИ типы, и на List<> со Stack<> промолчала:
# они из System.Collections.Generic. Добавляю самые ходовые — те, что я
# использую чаще всего и чаще всего забываю объявить.
echo "Проверка объявлений библиотеки:"
for f in $(find "$P" -name "*.cs"); do
  code=$(mktemp)
  sed 's://.*::; s:"[^"]*":"":g' "$f" > "$code"
  usings=$(grep "^using " "$f" | sed 's/^using //; s/;.*//' | tr -d " \r")
  for pair in "List<:System.Collections.Generic" "Dictionary<:System.Collections.Generic" \
              "HashSet<:System.Collections.Generic" "Stack<:System.Collections.Generic" \
              "Queue<:System.Collections.Generic" "StringBuilder:System.Text" \
              "Stopwatch:System.Diagnostics"; do
    t=${pair%%:*}; ns=${pair#*:}
    grep -q "$t" "$code" || continue
    grep -q "System.Collections.Generic.$t\|$ns\.$t" "$code" && continue
    echo "$usings" | grep -qx "$ns" || echo "  $(basename "$f"): $t — НЕТ using $ns"
  done
  rm -f "$code"
done
# ---- ССЫЛКИ НА НЕСУЩЕСТВУЮЩИЕ ТИПЫ ----
#
# Пробник подменяет LevelView3D и GameBootstrap заглушками, поэтому ссылки на
# УДАЛЁННЫЕ типы в них проходят насквозь. При удалении старого генератора это
# дало три ошибки сборки, которых ни одна проверка не увидела.
#
# Здесь для каждого типа с большой буквы, упомянутого в этих файлах, ищется
# объявление где-нибудь в проекте.
echo "Проверка ссылок на несуществующие типы:"
known="Vector2 Vector3 Vector2I Color Mesh Image Node Node3D Camera3D Material Shader
Godot System Math MathF Array List Dictionary HashSet Stack Queue String Func Action
Task Exception Guid DateTime StringBuilder Stopwatch Convert Environment Path File
Directory Encoding Enumerable Console Random Buffer Comparer Nullable Tuple Type
CanvasLayer DirectionalLight3D Label WorldEnvironment Environment3D MeshInstance3D
ArrayMesh SurfaceTool StandardMaterial3D ShaderMaterial ImageTexture Texture2D
MultiMesh MultiMeshInstance3D SubViewport Viewport Control Button VBoxContainer
HBoxContainer Container Panel PanelContainer Timer Sprite2D TextureRect
CompressedTexture2D DirAccess FileAccess ProjectSettings DisplayServer Engine
RenderingServer Transform3D Basis Aabb Plane Quaternion Rect2 Rect2I Vector4
CylinderMesh SphereMesh BoxMesh PlaneMesh Label3D QuadMesh PrismMesh TorusMesh"
for f in "$P/Presentation/Level/LevelView3D.cs" "$P/Bootstrap/GameBootstrap.cs"; do
  [ -f "$f" ] || continue
  code=$(mktemp)
  sed 's://.*::; s:"[^"]*":"":g' "$f" > "$code"
  # Только ОБЪЯВЛЕНИЯ и СОЗДАНИЕ: `Тип имя` и `new Тип(`. Обращения вида
  # Тип.Метод ловит проверить_методы.sh, а простой перебор слов с большой буквы
  # давал сотни ложных — он не отличает тип от имени метода или поля.
  { grep -oE "new +[A-Z][A-Za-z0-9_]{3,}" "$code" | sed "s/new *//"
    grep -oE "^ +(private|public|internal) +[A-Z][A-Za-z0-9_]{3,}[?]? " "$code" | awk "{print \$2}" | tr -d "?"
  } | sort -u | while read t; do
    echo "$known" | tr " \n" "\n\n" | grep -qx "$t" && continue
    grep -rqE "(class|struct|record|enum|interface) +$t\b" "$P" --include=*.cs && continue
    echo "  $(basename "$f"): $t — типа НЕТ в проекте"
  done
  rm -f "$code"
done
echo "готово"
