from datetime import date

from comedor_bot import build_message, find_day_menu, parse_weekly_menu

SAMPLE_HTML = """
<div class="field-item even">
  <h3>Campus de Cartuja (Facultad de Comunicación)</h3>
  <h4>Menú semanal: 15/06/2026 - 19/06/2026</h4>
  <table>
    <tr><th style="text-align:center; background-color:#951419; color:#fff" colspan=3><strong>LUNES 15/06/2026</strong></th></tr>
    <tr><th><strong>Primer plato</strong></th><th><strong>Segundo plato</strong></th><th><strong>Postre</strong></th></tr>
    <tr>
      <td>- Lentejas con calabaza y curry<br/>- Patatas aliñadas<br/></td>
      <td>- Calamares fritos<br/>- Chuleta de cerdo a la pimienta<br/></td>
      <td>- Fruta fresca<br/>- Postre casero/lácteo<br/></td>
    </tr>
    <tr><th style="text-align:center; background-color:#951419; color:#fff" colspan=3><span style="color:#fff;font-weight:bold;">MARTES 16/06/2026</span></th></tr>
    <tr><th><strong>Primer plato</strong></th><th><strong>Segundo plato</strong></th><th><strong>Postre</strong></th></tr>
    <tr>
      <td>- Ensalada de pasta<br/>- Guisantes<br/></td>
      <td>- Filete de cerdo en salsa verde<br/>- Fritura de boquerones<br/></td>
      <td>- Fruta fresca<br/>- Postre casero/lácteo <br/></td>
    </tr>
  </table>
</div>
"""


def test_parse_weekly_menu_extracts_columns():
    weekly_menu = parse_weekly_menu(SAMPLE_HTML)

    assert weekly_menu.campus == "Campus de Cartuja (Facultad de Comunicación)"
    assert weekly_menu.week_label == "Menú semanal: 15/06/2026 - 19/06/2026"
    assert len(weekly_menu.days) == 2
    assert weekly_menu.days[1].label == "MARTES"
    assert weekly_menu.days[1].menu_date == date(2026, 6, 16)
    assert weekly_menu.days[1].first_courses == ["Ensalada de pasta", "Guisantes"]
    assert weekly_menu.days[1].second_courses == ["Filete de cerdo en salsa verde", "Fritura de boquerones"]
    assert weekly_menu.days[1].desserts == ["Fruta fresca", "Postre casero/lácteo"]


def test_build_message_for_existing_day():
    weekly_menu = parse_weekly_menu(SAMPLE_HTML)
    day_menu = find_day_menu(weekly_menu, date(2026, 6, 16))

    message = build_message(weekly_menu, day_menu, date(2026, 6, 16), "https://sacu.us.es/menuSemanal?i=1")

    assert "Menu comedor US - 16/06/2026" in message
    assert "Primer plato:\n- Ensalada de pasta\n- Guisantes" in message
    assert "Segundo plato:\n- Filete de cerdo en salsa verde\n- Fritura de boquerones" in message
    assert "Postre:\n- Fruta fresca\n- Postre casero/lácteo" in message


def test_build_message_when_day_is_missing():
    weekly_menu = parse_weekly_menu(SAMPLE_HTML)

    message = build_message(weekly_menu, None, date(2026, 6, 20), "https://sacu.us.es/menuSemanal?i=1")

    assert "No hay menu publicado para esa fecha." in message
