from stp import stp_indicator, peak
import matplotlib.pyplot as plt
import pickle
from os import path
from datetime import timedelta
import pandas as pd


class StpDash(object):
    def __init__(self, data, tool_name, des_path='./', current_pk_t=4, current_lag=10, vb_pk_t=2, vb_lag=3,
                 normal_only=True, after_swap_only=False):
        """
        To generate an overview for STP indicators in one dash

        :param data: dataframe extract from data warehouse and transform into columns as features
        :param tool_name: str, pump name
        :param des_path: str, path of folder to save the dash
        :param current_pk_t: float, std threshold to detect current spike
        :param current_lag: int, with in lag number of data points, count one spike
        :param vb_pk_t: float, std threshold to detect vibration b spike
        :param vb_lag: int, with in lag number of data points, count one spike
        :param normal_only: bool, if true, only use operation data where Equipment status is Normal
        :param after_swap_only: bool, if true, only use data after swapping the pump
        """
        self.data = data
        self.tool_name = tool_name
        self.des_path = des_path
        self.current_pk_t = current_pk_t
        self.current_lag = current_lag
        self.vb_pk_t = vb_pk_t
        self.vb_lag = vb_lag
        self.normal = normal_only
        self.after_swap = after_swap_only

    def plot_indicators(self):
        """
        To plot all indicators on one dash

        :return: fig
        """
        data = self.data
        tool_name = self.tool_name
        stp = stp_indicator.StpIndicators(data, self.after_swap)
        # 2 TMS control cycle
        try:
            tms_period = stp.tms_period()
        except IndexError:
            tms_period = None
        # 3 Motor Current Trend
        current_trend_ma = stp.motor_current_trend(bin_size=1000)
        current_trend_sk, _ = stp.motor_current_spike(99, self.current_pk_t)
        # current_trend_l1 = stp.motor_current_trend(method='l1')
        # 4 Rotor blade contact
        try:
            assert 'Motor Current' in data.columns
            assert 'Vibration B' in data.columns
            _, current_pk_count = peak.PeakDetect.spike_detect(data['Motor Current'].dropna(), 99, self.current_pk_t,
                                                               self.current_lag, 'Motor Current', plot=False)
            _, vb_pk_count = peak.PeakDetect.spike_detect_local(data[data['Vibration B'] < 0.1]['Vibration B'].dropna(),
                                                                99, self.vb_pk_t, self.vb_lag,
                                                                'Vibration B', plot=False)
        except AssertionError:
            current_pk_count, vb_pk_count = None, None
        large_contact, small_contact = stp.rotor_contact(normal=self.normal, current_pk_t=self.current_pk_t,
                                                         vb_pk_t=self.vb_pk_t, current_lag=self.current_lag,
                                                         v_lag=self.vb_lag)
        # 5 Vibration anomaly score
        vib_anomaly = stp.vib_anomaly_score()
        # 6 Rotor blade contact during deceleration
        dec_period = stp.dec_period()
        # 7 Start anomaly score
        start_anomaly = stp.start_anomaly_score()

        d = dict(tms_period=tms_period, current_trend_ma=current_trend_ma,
                 current_pk_count=current_pk_count, large_contact=large_contact,
                 small_contact=small_contact, vib_anomaly=vib_anomaly,
                 dec_period=dec_period, start_anomaly=start_anomaly)
        D = pd.DataFrame(dict([(k, pd.Series(v)) for k, v in d.items()]))
        # 8 Rotor shaft displacement
        data_dis = stp.rotor_shaft_displacement()
        self.indicators = pd.concat([D, data_dis])
        # 9 Motor Temperature
        try:
            assert 'Motor Temperature' in data.columns
            temp_trend_ma = data['Motor Temperature'].dropna().rolling(1000).mean()
        except AssertionError:
            temp_trend_ma = None

        fig, axes = plt.subplots(3, 3, sharex=True, squeeze=True, figsize=(16, 9))
        fig.suptitle(tool_name, y=0.95)
        if data_dis is not None:
            ind_c = data_dis[data_dis['Equipment Status'] > 0].index
            yb = data_dis[data_dis['Equipment Status'] > 0]['dXYb_abs']
            cb = data_dis[data_dis['Equipment Status'] > 0]['Equipment Status']
            img = axes[0][1].scatter(x=ind_c, y=yb, alpha=0.5, c=cb, cmap='gist_rainbow')
            axes[0][1].set_ylabel('Rotor Shaft Displacement-Bottom')
            axes[0][1].set_ylim([0, 2])
            axes[0][1].grid()

            yh = data_dis[data_dis['Equipment Status'] > 0]['dXYh_abs']
            ch = data_dis[data_dis['Equipment Status'] > 0]['Equipment Status']
            img = axes[0][0].scatter(x=ind_c, y=yh, alpha=0.5, c=ch, cmap='gist_rainbow')
            axes[0][0].set_ylabel('Rotor Shaft Displacement-Head')
            axes[0][0].set_ylim([0, 2])
            axes[0][0].grid()
            fig.colorbar(img, ax=axes[0][1], anchor=(0, 0))
        try:
            assert 'Motor Current' in data.columns
            motor_current = data['Motor Current'].dropna()
            axes[0][2].plot(motor_current, alpha=0.5)
            axes[0][2].plot(current_trend_ma, alpha=0.5)
            axes[0][2].plot(current_pk_count.keys(),
                            [motor_current.loc[i] for i in current_pk_count.keys()],
                            'o', c='r', alpha=0.5)
            # axes[0][2].plot(current_trend_l1, label='Trend_L1', alpha=0.5)
            axes[0][2].set_ylabel('Motor Current')
            axes[0][2].set_ylim([0, 20])
            axes[0][2].grid()
        except AssertionError:
            pass
        try:
            if (tms_period is not None) and (max(tms_period.values()) > 500):
                try:
                    axes[1][0].plot([i for i in tms_period.keys()], [i for i in tms_period.values()])
                    axes[1][0].set_ylabel('TMS Temperature Cycle in s')
                    axes[1][0].set_ylim([800, 2400])
                    axes[1][0].grid()
                except ValueError:
                    pass
        except KeyError:
            pass
        try:
            assert 'Motor Temperature' in data.columns
            if len(data['Motor Temperature']) > 0:
                motor_temp = data['Motor Temperature'].dropna()
                axes[1][1].plot(motor_temp - 273.15, alpha=0.5, linewidth=2)
                axes[1][1].plot(temp_trend_ma - 273.15, label='Trend_MA', alpha=0.5, linewidth=2)
            axes[1][1].set_ylabel('Motor Temperature')
            axes[1][1].set_ylim([20, 120])
            axes[1][1].grid()
        except AssertionError:
            pass
        try:
            assert 'Vibration B' in data.columns
            assert 'Vibration H' in data.columns
            if len(data['Vibration B']) > 0:
                vib_h = data['Vibration H'].dropna()
                vib_b = data['Vibration B'].dropna()
                axes[1][2].plot(vib_h, label='Vibration H', alpha=0.8, linewidth=2)
                axes[1][2].plot(vib_b, label='Vibration B', alpha=0.8, linewidth=2)
                axes[1][2].plot(vb_pk_count.keys(),
                                [vib_b.loc[i] for i in vb_pk_count.keys()],
                                'o', c='r', alpha=0.5)
            # axes[1][2].set_ylabel('Vibration')
            axes[1][2].set_ylim([0, 12e-5])
            axes[1][2].grid()
            axes[1][2].legend(loc='upper left')
        except AssertionError:
            pass
        if vib_anomaly is not None:
            axes[2][0].plot([i for i in vib_anomaly.keys()], [i for i in vib_anomaly.values()], label='Vibration')
        if start_anomaly is not None:
            axes[2][0].plot([i for i in start_anomaly.keys()], [i for i in start_anomaly.values()], label='Start Event')
            axes[2][0].set_ylabel('Anomaly Score')
            axes[2][0].set_ylim([0, 1.1])
            axes[2][0].grid()
            axes[2][0].legend(loc='upper left')

        if dec_period is not None:
            axes[2][1].plot([i for i in dec_period.keys()], [i for i in dec_period.values()])
            axes[2][1].set_ylabel('Time to Stop in s')
            axes[2][1].set_ylim([0, 600])
            axes[2][1].grid()

        if large_contact is not None and small_contact is not None:
            axes[2][2].plot([i for i in large_contact.keys()], [i for i in large_contact.values()], label='Large')
            axes[2][2].plot([i for i in small_contact.keys()], [i for i in small_contact.values()], label='Small')
            axes[2][2].set_ylabel('Rotor Contact During Operation')
            axes[2][2].grid()
            axes[2][2].set_ylabel('Contact')
            axes[2][2].legend(loc='upper left')

        plt.xlim(min(self.data.index) - timedelta(days=2), max(self.data.index) + timedelta(days=2))

        _ = plt.setp(axes[2][0].xaxis.get_majorticklabels(), rotation=25)
        _ = plt.setp(axes[2][1].xaxis.get_majorticklabels(), rotation=25)
        _ = plt.setp(axes[2][2].xaxis.get_majorticklabels(), rotation=25)

        return fig, self.indicators

    def save_plot(self):
        """
        To save the dash into destination folder

        :return:
        """

        fig, indicators = self.plot_indicators()

        with open(path.join(self.des_path, '{}.pkl'.format(self.tool_name)), 'wb') as fid:
            pickle.dump(fig, fid)
        fig.savefig(path.join(self.des_path, '{}.png'.format(self.tool_name)))

        csv_path = path.join(self.des_path, '{}.csv'.format(self.tool_name))
        indicators.to_csv(csv_path, index_label='LogTime')