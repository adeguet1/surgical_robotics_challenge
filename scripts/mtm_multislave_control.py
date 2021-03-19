#!/usr/bin/env python
# //==============================================================================
# /*
#     Software License Agreement (BSD License)
#     Copyright (c) 2019
#     (aimlab.wpi.edu)

#     All rights reserved.

#     Redistribution and use in source and binary forms, with or without
#     modification, are permitted provided that the following conditions
#     are met:

#     * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.

#     * Redistributions in binary form must reproduce the above
#     copyright notice, this list of conditions and the following
#     disclaimer in the documentation and/or other materials provided
#     with the distribution.

#     * Neither the name of authors nor the names of its contributors may
#     be used to endorse or promote products derived from this software
#     without specific prior written permission.

#     THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#     "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#     LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
#     FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
#     COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
#     INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
#     BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#     LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
#     CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
#     LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
#     ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
#     POSSIBILITY OF SUCH DAMAGE.

#     \author    <aimlab.wpi.edu>
#     \author    <amunawar@wpi.edu>
#     \author    Adnan Munawar
#     \version   1.0
# */
# //==============================================================================
from psmIK import *
from ambf_client import Client
from psm_arm import PSM
import time
import rospy
import PyKDL
from PyKDL import Frame, Rotation, Vector
from argparse import ArgumentParser
from mtm_device import MTM
from itertools import cycle


class ControllerInterface:
    def __init__(self, master, slave_arms, T_c_w):
        self.counter = 0
        self.master = master
        self.slave_arms = cycle(slave_arms)
        self.active_salve = self.slave_arms.next()

        self.cmd_xyz = self.active_salve.T_t_b_home.p
        self.cmd_rpy = None
        self.T_IK = None
        self.T_c_w = T_c_w

        self._T_c_b = None
        self._T_c_b_updated = False

    def switch_slave(self):
        self._T_c_b_updated = False
        self.active_salve = self.slave_arms.next()
        print('Switching Control of Next Slave Arm: ', self.active_salve.name)

    def update_T_b_c(self):
        if not self._T_c_b_updated:
            self._T_c_b = self.active_salve.get_T_w_b() * self.T_c_w
            self._T_c_b_updated = True

    def update_arm_pose(self):
        self.update_T_b_c()
        if self.master.coag_button_pressed or self.master.clutch_button_pressed:
            self.master.optimize_wrist_platform()
        else:
            if self.master.is_active():
                self.master.move_cp(self.master.pre_coag_pose_msg)
        twist = self.master.measured_cv() * 0.35
        self.cmd_xyz = self.active_salve.T_t_b_home.p
        if not self.master.clutch_button_pressed:
            delta_t = self._T_c_b.M * twist.vel
            self.cmd_xyz = self.cmd_xyz + delta_t
            self.active_salve.T_t_b_home.p = self.cmd_xyz
        self.cmd_rpy = self._T_c_b.M * self.master.measured_cp().M
        self.T_IK = Frame(self.cmd_rpy, self.cmd_xyz)
        self.active_salve.move_cp(self.T_IK)
        self.active_salve.set_jaw_angle(self.master.get_jaw_angle())
        # self.active_salve.run_grasp_logic(self.master.get_jaw_angle())

    def update_visual_markers(self):
        # Move the Target Position Based on the GUI
        if self.active_salve.target_IK is not None:
            T_t_w = self.active_salve.get_T_b_w() * self.T_IK
            self.active_salve.target_IK.set_pos(T_t_w.p[0], T_t_w.p[1], T_t_w.p[2])
            self.active_salve.target_IK.set_rpy(T_t_w.M.GetRPY()[0], T_t_w.M.GetRPY()[1], T_t_w.M.GetRPY()[2])
        # if self.arm.target_FK is not None:
        #     ik_solution = self.arm.get_ik_solution()
        #     ik_solution = np.append(ik_solution, 0)
        #     T_7_0 = convert_mat_to_frame(compute_FK(ik_solution))
        #     T_7_w = self.arm.get_T_b_w() * T_7_0
        #     P_7_0 = T_7_w.p
        #     RPY_7_0 = T_7_w.M.GetRPY()
        #     self.arm.target_FK.set_pos(P_7_0[0], P_7_0[1], P_7_0[2])
        #     self.arm.target_FK.set_rpy(RPY_7_0[0], RPY_7_0[1], RPY_7_0[2])

    def run(self):
        if self.master.switch_slave:
            self.switch_slave()
            self.master.switch_slave = False
        self.update_arm_pose()
        # self.update_visual_markers()


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('-c', action='store', dest='client_name', help='Client Name', default='ambf_client')
    parser.add_argument('--one', action='store', dest='run_psm_one', help='Control PSM1', default=True)
    parser.add_argument('--two', action='store', dest='run_psm_two', help='Control PSM2', default=True)
    parser.add_argument('--three', action='store', dest='run_psm_three', help='Control PSM3', default=True)
    parser.add_argument('--mtm', action='store', dest='mtm_name', help='Name of MTM to Bind', default='/dvrk/MTMR/')

    parsed_args = parser.parse_args()
    print('Specified Arguments')
    print(parsed_args)

    mtm_valid_list = ['/MTMR/, /MTML/', '/dvrk/MTMR/', '/dvrk/MTML/', 'MTMR', 'MTML']
    if parsed_args.mtm_name in mtm_valid_list:
        if parsed_args.mtm_name in ['MTMR', 'MTML']:
            parsed_args.mtm_name = '/' + parsed_args.mtm_name + '/'
    else:
        print('ERROR! --mtm argument should be one of the following', mtm_valid_list)
        raise ValueError

    if parsed_args.run_psm_one in ['True', 'true', '1']:
        parsed_args.run_psm_one = True
    elif parsed_args.run_psm_one in ['False', 'false', '0']:
        parsed_args.run_psm_one = False

    if parsed_args.run_psm_two in ['True', 'true', '1']:
        parsed_args.run_psm_two = True
    elif parsed_args.run_psm_two in ['False', 'false', '0']:
        parsed_args.run_psm_two = False
    if parsed_args.run_psm_three in ['True', 'true', '1']:
        parsed_args.run_psm_three = True
    elif parsed_args.run_psm_three in ['False', 'false', '0']:
        parsed_args.run_psm_three = False

    c = Client(parsed_args.client_name)
    c.connect()

    cam_frame = c.get_obj_handle('CameraFrame')
    time.sleep(0.5)
    P_c_w = cam_frame.get_pos()
    R_c_w = cam_frame.get_rpy()

    T_c_w = Frame(Rotation.RPY(R_c_w[0], R_c_w[1], R_c_w[2]), Vector(P_c_w.x, P_c_w.y, P_c_w.z))
    print(T_c_w)

    controllers = []
    slave_arms = []

    if parsed_args.run_psm_one is True:
        # Initial Target Offset for PSM1
        # init_xyz = [0.1, -0.85, -0.15]
        arm_name = 'psm1'
        print('LOADING CONTROLLER FOR ', arm_name)
        psm = PSM(c, arm_name)
        if psm.is_present():
            T_psmtip_c = Frame(Rotation.RPY(3.14, 0.0, -1.57079), Vector(-0.2, 0.0, -1.0))
            T_psmtip_b = psm.get_T_w_b() * T_c_w * T_psmtip_c
            psm.set_home_pose(T_psmtip_b)
            slave_arms.append(psm)

    if parsed_args.run_psm_two is True:
        # Initial Target Offset for PSM1
        # init_xyz = [0.1, -0.85, -0.15]
        arm_name = 'psm2'
        print('LOADING CONTROLLER FOR ', arm_name)
        theta_base = -0.7
        psm = PSM(c, arm_name)
        if psm.is_present():
            T_psmtip_c = Frame(Rotation.RPY(3.14, 0.0, -1.57079), Vector(0.2, 0.0, -1.0))
            T_psmtip_b = psm.get_T_w_b() * T_c_w * T_psmtip_c
            psm.set_home_pose(T_psmtip_b)
            slave_arms.append(psm)

    if parsed_args.run_psm_three is True:
        # Initial Target Offset for PSM1
        # init_xyz = [0.1, -0.85, -0.15]
        arm_name = 'psm3'
        print('LOADING CONTROLLER FOR ', arm_name)
        psm = PSM(c, arm_name)
        if psm.is_present():
            slave_arms.append(psm)

    if len(slave_arms) == 0:
        print('No Valid PSM Arms Specified')
        print('Exiting')

    else:
        master = MTM(parsed_args.mtm_name)
        master.set_base_frame(Frame(Rotation.RPY((np.pi - 0.8) / 2, 0, 0), Vector(0, 0, 0)))
        controller1 = ControllerInterface(master, slave_arms, T_c_w)
        controllers.append(controller1)

        rate = rospy.Rate(200)

        while not rospy.is_shutdown():
            for cont in controllers:
                cont.run()
            rate.sleep()

