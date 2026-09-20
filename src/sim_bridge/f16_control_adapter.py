"""Connect the stock F-16 surfaces to an external attitude controller."""


def apply_external_controls(tree):
    fcs = tree.find('flight_control')
    roll = fcs.find("channel[@name='Roll']")
    # The stock aerodynamic aileron property bypasses its FBW override switch.
    # Read the physical, speed-compensated surface after the actuator instead.
    control = roll.find("aerosurface_scale[@name='fcs/aileron-control']")
    control.find('input').text = 'fcs/aileron-speed-compensated'
    roll.remove(control)
    roll.append(control)
    # The stock yaw scheduler has no FBW override at all. Keep trim and the
    # actuator dynamics, but let ArduPilot provide the feedback correction.
    yaw = fcs.find("channel[@name='Yaw']")
    scheduler = yaw.find("summer[@name='fcs/yaw-scheduler']")
    for item in list(scheduler.findall('input')):
        if item.text == 'fcs/yaw-load-pid':
            scheduler.remove(item)
