import pywinauto
from pywinauto import Desktop
import time

app = Desktop(backend='uia').window(title_re='PB_studio.*')
app.set_focus()
time.sleep(0.3)

descendants = app.descendants()
print(f'Total descendants: {len(descendants)}')

for d in descendants:
    try:
        rect = d.rectangle()
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        name = d.window_text()
        ctrl_type = str(d.element_info.control_type)
        if cx > 1900 and cy > 350 and cy < 800:
            print(f'{ctrl_type} | {repr(name[:60])} | cx={cx},cy={cy} | rect=({rect.left},{rect.top},{rect.right},{rect.bottom})')
    except Exception as e:
        pass
