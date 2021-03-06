# -*- coding: utf-8 -*-
"""openBCIEGG.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1e5UIPSXmaaLpUec42N9wPGgjwzLCOUop
"""

import numpy as np
import scipy as sp
import scipy.io
from scipy.ndimage import gaussian_filter
from scipy import signal

import pandas as pd
import time, datetime, sys, os

import matplotlib.mlab as mlab
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
#!pip3 install pykalman
from pykalman import KalmanFilter
from numpy import ma

import seaborn as sns
sns.set(rc={'image.cmap': 'jet'},style="whitegrid",font_scale=1.2)

class openBCIEGG:
    fsRaw = 250
    fsEGG = 1
    def __init__(self,directory,RID,fIncludeChannels=True,fUsePowerEGG=False,epsilonKF=1e-7,fSensorLocFilePresent=False):
        self.RID = RID
        self.EGGmatrix = np.array([])
        self.ImportCSVData(directory,RID,fIncludeChannels,fSensorLocFilePresent)
        self.EGG_estimate, self.errorBars =self.PerformKalmanEstimationArtifacts(self.dfEGG,
                                                                                 epsilon=epsilonKF,
                                                                                 fUsePowerEGG=fUsePowerEGG)
        

    def ExtractEventTypes(self,dfEvents,dtEvents):
        eventType = np.zeros(len(dtEvents))
        for ii in range(0,eventType.size):
            if dfEvents['Event Type'][ii]=='I just started to record': eventType[ii]=1
            if dfEvents['Event Type'][ii]=='I just woke up': eventType[ii]=2
            if dfEvents['Event Type'][ii]=='I just ate a meal': eventType[ii]=3
            if dfEvents['Event Type'][ii]=='I just ate a snack': eventType[ii]=4
            if dfEvents['Event Type'][ii]=='I just had a bowel movement': eventType[ii]=5
            if dfEvents['Event Type'][ii]=='I\'m having symptoms': eventType[ii]=6
            if dfEvents['Event Type'][ii]=='I\'m going to sleep soon': eventType[ii]=7
            if dfEvents['Event Type'][ii]=='I just stopped recording': eventType[ii]=8
            if dfEvents['Event Type'][ii]=='Other': eventType[ii]=9                
        return eventType


    def ImportCSVData(self,directory,RID,fIncludeChannels=False,fSensorLocFilePresent=False):
        if (fIncludeChannels):        
            self.dfEGGchannels = pd.read_csv(directory+RID+'-EGGchannels.csv')
        else:
            self.dfEGGchannels = []

        if (fSensorLocFilePresent):
            self.dfSensorLoc = pd.read_csv(directory+RID+'-SensorLoc.csv')
        else:
            self.dfSensorLoc = []
        self.dfEGG = pd.read_csv(directory+RID+'-EGG.csv')
        self.dtEGG = pd.to_datetime(np.array(self.dfEGG['Timestamp']))

        self.dfHR = pd.read_csv(directory+RID+'-HR.csv')
        self.dtHR = pd.to_datetime(np.array(self.dfHR['Timestamp']))

        self.dfAccel = pd.read_csv(directory+RID+'-ACC.csv')
        self.dtAccel = pd.to_datetime(np.array(self.dfAccel['Timestamp']))

        self.dfEvents = pd.read_csv(directory+RID+'-events.csv')
        self.dtEvents = pd.to_datetime(np.array(self.dfEvents['Timestamp']))

        #EVENT TYPES
        self.eventType = self.ExtractEventTypes(self.dfEvents,self.dtEvents)

    def extractEGGmatrix(self,fVerbose=False):
        matrix = self.dfEGGchannels.values

        # first few rows of column 1
        self.EGGmatrix = matrix[:,2:10]
        if (fVerbose):
            # first few rows of column 0
            print('first few rows of column 0 = ', matrix[0:10,0])
            # first few rows of column 1
            print('first few rows of column 1 = ', matrix[0:10,1])            
        # first few rows of column 1
        self.EGGmatrix = np.copy(matrix[:,2:10])
        if (fVerbose):
            print('eliminating those first 2 columns.  EGG matrix shape = ', self.EGGmatrix.shape)
        return self.EGGmatrix

    def KalmanEGGpowerMask(self,powerEGG,artifact_indices,useEMstateTransitionVariance,epsilon,n_iter=3):
        length_vec = powerEGG.shape[0]
        measurements = ma.asarray(np.copy(powerEGG)) 
        measurements[artifact_indices] =ma.masked

        if (useEMstateTransitionVariance):
            em_varsVec = ['initial_state_mean',  'initial_state_covariance','transition_covariance']
            kf = KalmanFilter(observation_matrices = 1.0,observation_covariance=epsilon,\
                              transition_matrices = 1.0, transition_offsets=0.0, \
                              observation_offsets = 0.0,\
                              em_vars = em_varsVec)
        else:
            R = np.var(np.diff(measurements[artifact==False]))
            em_varsVec = ['initial_state_mean',  'initial_state_covariance']
            kf = KalmanFilter(observation_matrices = 1.0,observation_covariance=epsilon,\
                              transition_matrices = 1.0, transition_offsets=0.0, transition_covariance=R, \
                              observation_offsets = 0.0,\
                              em_vars = em_varsVec)

        kf = kf.em(measurements, n_iter=n_iter)
        (smoothed_state_means, smoothed_state_covariances) = kf.smooth(measurements)

        return np.squeeze(smoothed_state_means), np.squeeze(smoothed_state_covariances)

    def PerformKalmanEstimationArtifacts(self,dfEGG,epsilon=1e-7,fUsePowerEGG=True):
        if (fUsePowerEGG):
            waveform = np.array(dfEGG['Raw EGG Power (dB)'])
        else:
            waveform = np.array(dfEGG['Normalized EGG Power (dB)'])
        artifact = np.array(dfEGG['Artifact'])

        artifact_indices = np.where(artifact==True)[0]
        epsilon = 1e-7
        (smoothed_state_means, smoothed_state_covariances) =self.KalmanEGGpowerMask(waveform,artifact_indices,True,epsilon,3)
        return smoothed_state_means, smoothed_state_covariances

    def PlotStuff(self,colorSleep='red',colorErrorBars='red',fUseTitle=False,fSaveFig=False):
        fig,ax = plt.subplots(nrows=5,figsize=(10,10))
        cm = plt.cm.get_cmap('jet')
#         fsEGG=1
        window = self.fsEGG*60*5

        s1 = ax[0].specgram(self.dfEGGchannels['Best Pair'],
                         NFFT=window,Fs=self.fsEGG,noverlap=window*.75,interpolation='none',cmap=cm)
        ax[0].axis('tight')
        ax[0].set_ylim([0.02,0.15])
        ax[0].set_ylabel('Frequency (Hz)')
        ax[0].grid(None)
        ax[0].axes.xaxis.set_ticklabels([])
        s1[3].set_clim(25,55)
        cbar_ax0 = fig.add_axes([.915, 0.742, 0.016, 0.138])
        cb = plt.colorbar(s1[3],cax=cbar_ax0,ax=ax[0])
        
        #plot events
        dtEvents = self.dtEvents
        eventType = self.eventType
        for ii in range(1,4):
            [ax[ii].axvline(dtEvents[np.where(eventType==3)][j],lw=3,color=sns.color_palette()[1],
                            label='meal' if j==0 else "")
             for j in range(0,np.sum(eventType==3))]
            [ax[ii].axvline(dtEvents[np.where(eventType==4)][j],lw=3,alpha=0.4,color=sns.color_palette()[1],
                            label='snack' if j==0 else "")
             for j in range(0,np.sum(eventType==4))]
            [ax[ii].axvline(dtEvents[np.where(eventType==5)][j],lw=3,color=sns.color_palette()[5],
                            label='bowel movement' if j==0 else "")
             for j in range(0,np.sum(eventType==5))]
            [ax[ii].axvline(dtEvents[np.where(eventType==6)][j],lw=3,color=sns.color_palette()[2],
                            label='symptom' if j==0 else "")
             for j in range(0,np.sum(eventType==6))]
            [ax[ii].axvline(dtEvents[np.where(eventType==9)][j],lw=3,color=sns.color_palette()[4],
                            label='other' if j==0 else "")
             for j in range(0,np.sum(eventType==9))]
            sleepStart = np.where(eventType==7)[0]
            sleepStop = np.where(eventType==2)[0]
            [ax[ii].axvspan(dtEvents[sleepStart[j]],dtEvents[sleepStop[j]],color=colorSleep,
                            alpha=0.15,label='sleep' if j==0 else "")
             for j in range(0,np.minimum(sleepStart.size,sleepStop.size))]
            ax[ii].set_xlim([self.dtEGG[0],self.dtEGG[-1]])

        # draw artifacts
        timesOfArtifacts = self.dtEGG[self.dfEGG['Artifact']]
        ax[1].plot(self.dtEGG,self.EGG_estimate,label='')
        [ax[1].axvline(timesOfArtifacts[j],lw=2,color='grey',alpha=0.15)
         for j in range(0,len(timesOfArtifacts))]
        ax[1].fill_between(self.dtEGG,
                         self.EGG_estimate-self.errorBars/2,
                         self.EGG_estimate+self.errorBars/2, alpha = 0.4,color=colorErrorBars)
        ax[1].set_ylabel('EGG Power (dB)')
        ax[1].legend(bbox_to_anchor=(1,1),loc=2,borderaxespad=0)
        ax[1].axes.xaxis.set_ticklabels([])



        ax[2].plot(self.dtHR,self.dfHR['RMSSD (ms)'])
        ax[2].set_ylabel('HRV: (RMSSD, ms)')
        ax[2].axes.xaxis.set_ticklabels([])

        ax[3].plot(self.dtHR,self.dfHR['HR (bpm)'])
        ax[3].set_ylabel('HR (bpm)')
        ax[3].axes.xaxis.set_ticklabels([])

        ax[4].plot(self.dtAccel,self.dfAccel['AccY'])
        ax[4].set_ylabel('Accel (Y)')


        ax[4].set_xticklabels(ax[4].xaxis.get_majorticklabels(),rotation=30,ha='right')
        ax[4].xaxis.set_major_formatter(mdates.DateFormatter('%m/%d/%y - %H:%M'))
        ax[4].set_xlabel('Date - Time')
#         fig.tight_layout()
        if (fUseTitle):
            ax[0].set_title(self.RID)

        if (fSaveFig):
            plt.savefig('./Export/'+self.RID+'.png',dpi=100,bbox_inches='tight')
        return fig, ax

