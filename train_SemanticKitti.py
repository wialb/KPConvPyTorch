#
#
#      0=================================0
#      |    Kernel Point Convolutions    |
#      0=================================0
#
#
# ----------------------------------------------------------------------------------------------------------------------
#
#      Callable script to start a training on SemanticKitti dataset
#
# ----------------------------------------------------------------------------------------------------------------------
#
#      Hugues THOMAS - 06/03/2020
#


# ----------------------------------------------------------------------------------------------------------------------
#
#           Imports and global variables
#       \**********************************/
#

# Common libs
import signal
import os
import numpy as np
import sys
import torch

# Dataset
from datasets.SemanticKitti import * # i.e. class[SemanticKittiDataset, SemanticKittiSampler, SemanticKittiCustomBatch], def[SemanticKittiCollate, debug_timing, debug_class_w]
from torch.utils.data import DataLoader

from utils.config import Config
from utils.trainer import ModelTrainer
from models.architectures import KPFCNN

import wandb

# ----------------------------------------------------------------------------------------------------------------------
#
#           Config Class
#       \******************/
#

class SemanticKittiConfig(Config):
    """
    Override the parameters you want to modify for this dataset
    """

    ####################
    # Dataset parameters
    ####################

    # Dataset name
    dataset = 'Kitti-360'

    # Number of classes in the dataset (This value is overwritten by dataset class when Initializating dataset).
    num_classes = None

    # Type of task performed on this dataset (also overwritten)
    dataset_task = ''

    #########################
    # Architecture definition
    #########################

    # Define layers
    architecture = ['simple',
                    'resnetb',
                    'resnetb_strided',
                    'resnetb',
                    'resnetb',
                    'resnetb_strided',
                    'resnetb',
                    'resnetb',
                    'resnetb_strided',
                    'resnetb_deformable',
                    'resnetb_deformable',
                    'resnetb_deformable_strided',
                    'resnetb_deformable',
                    'resnetb_deformable',
                    'nearest_upsample',
                    'unary',
                    'nearest_upsample',
                    'unary',
                    'nearest_upsample',
                    'unary',
                    'nearest_upsample',
                    'unary']

    ###################
    # KPConv parameters
    ###################

    # Radius of the input sphere
    in_radius = 15.0
    val_radius = 15.0
    n_frames = 1
    max_in_points = 12000
    max_val_points = 12000

    # Number of batch
    batch_num = 1
    val_batch_num = 1

    # Number of kernel points
    num_kernel_points = 15

    # Size of the first subsampling grid in meter
    first_subsampling_dl = 0.1 

    # Radius of convolution in "number grid cell". (2.5 is the standard value)
    conv_radius = 2.5

    # Radius of deformable convolution in "number grid cell". Larger so that deformed kernel can spread out
    deform_radius = 4.0

    # Radius of the area of influence of each kernel point in "number grid cell". (1.0 is the standard value)
    KP_extent = 1.0

    # Behavior of convolutions in ('constant', 'linear', 'gaussian')
    KP_influence = 'linear'

    # Aggregation function of KPConv in ('closest', 'sum')
    aggregation_mode = 'sum'

    # Choice of input features
    first_features_dim = 128
    in_features_dim = 1#2

    # Can the network learn modulations
    modulated = False

    # Batch normalization parameters
    use_batch_norm = True
    batch_norm_momentum = 0.02

    # Deformable offset loss
    # 'point2point' fitting geometry by penalizing distance from deform point to input points
    # 'point2plane' fitting geometry by penalizing distance from deform point to input point triplet (not implemented)
    deform_fitting_mode = 'point2point'
    deform_fitting_power = 1.0              # Multiplier for the fitting/repulsive loss
    deform_lr_factor = 0.1                  # Multiplier for learning rate applied to the deformations
    repulse_extent = 1.2                    # Distance of repulsion for deformed kernel points

    #####################
    # Training parameters
    #####################

    # Maximal number of epochs
    max_epoch = 500

    # Learning rate management
    learning_rate = 1e-3
    momentum = 0.98
    lr_decays = {i: 0.1 ** (1 / 150) for i in range(1, max_epoch)}
    
    
    grad_clip_norm = 100.0

    # Number of steps per epochs
    epoch_steps = 600

    # Number of validation examples per epoch
    validation_size = 100

    # Number of epoch between each checkpoint
    checkpoint_gap = 10

    # Augmentations
    augment_scale_anisotropic = True
    augment_symmetries = [True, False, False]
    augment_scale_min = 0.8
    augment_scale_max = 1.2
    augment_rotation = 'vertical'
    augment_noise = 0.001
    #augment_color = 0.8

    # Choose weights for class (used in segmentation loss). Empty list for no weights
    # class proportion for R=10.0 and dl=0.08 (first is unlabeled)
    # 19.1 48.9 0.5  1.1  5.6  3.6  0.7  0.6  0.9 193.2 17.7 127.4 6.7 132.3 68.4 283.8 7.0 78.5 3.3 0.8
    #
    #

    # sqrt(Inverse of proportion * 100)
    # class_w = [1.430, 14.142, 9.535, 4.226, 5.270, 11.952, 12.910, 10.541, 0.719,
    #            2.377, 0.886, 3.863, 0.869, 1.209, 0.594, 3.780, 1.129, 5.505, 11.180]

    # sqrt(Inverse of proportion * 100)  capped (0.5 < X < 5)
    # class_w = [1.430, 5.000, 5.000, 4.226, 5.000, 5.000, 5.000, 5.000, 0.719, 2.377,
    #            0.886, 3.863, 0.869, 1.209, 0.594, 3.780, 1.129, 5.000, 5.000]

    # Do we need to save convergence
    saving = True
    saving_path = None


# ----------------------------------------------------------------------------------------------------------------------
#
#           Main Call
#       \***************/
#

if __name__ == '__main__':
    
    user = "william-albert124"
    project = "KPConv_PyTorch"
    display_name = "CATEG-2023-10-19_FT2"
    notes = "void, flat, construction, object, vegetation, building, vehicle"

    wandb.init(entity=user, project=project, name=display_name, notes=notes)
    
    os.system("nvidia-settings -a \"[gpu:0]/GPUFanControlState=1\" -a \"[fan:0]/GPUTargetFanSpeed=70\" -a \"[fan:1]/GPUTargetFanSpeed=70\"")
    os.system("nvidia-settings -a \"[gpu:0]/GPUFanControlState=1\" -a \"[fan:0]/GPUTargetFanSpeed=70\" -a \"[fan:1]/GPUTargetFanSpeed=70\"")
    
    ############################
    # Initialize the environment
    ############################

    # Set which gpu is going to be used
    GPU_ID = '0'

    # Set GPU visible device
    os.environ['CUDA_VISIBLE_DEVICES'] = GPU_ID

    ###############
    # Previous chkp
    ###############

    # Choose here if you want to start training from a previous snapshot (None for new training)
    # previous_training_path = 'Log_2020-03-19_19-53-27'
    previous_training_path = 'Log_2023-05-31_18-32-23'#''

    # Choose index of checkpoint to start from. If None, uses the latest chkp
    chkp_choice = 'chkp_best_mVal_IoU.tar' #None
    if previous_training_path:

        # Find all snapshot in the chosen training folder
        chkp_path = os.path.join('results', previous_training_path, 'checkpoints')
        #chkps = [f for f in os.listdir(chkp_path)  if f[:4] == 'chkp']

        # Find which snapshot to restore
        if chkp_choice is None:
            chosen_chkp = 'current_chkp.tar'
        else:
            chosen_chkp = chkp_choice
        chosen_chkp = os.path.join('results', previous_training_path, 'checkpoints', chosen_chkp)

    else:
        chosen_chkp = None
    
    print(chosen_chkp)
    ##############
    # Prepare Data
    ##############

    print()
    print('Data Preparation')
    print('****************')

    # Initialize configuration class
    config = SemanticKittiConfig()
    if previous_training_path:
        config.load(os.path.join('results', previous_training_path))
        config.saving_path = None

    # Get path from argument if given
    if len(sys.argv) > 1:
        config.saving_path = sys.argv[1]
        
    ft = True
    if ft:
        config.learning_rate = 1e-3
        config.epoch_steps = 75
        config.validation_size = 13
        config.max_epoch = 15

    # Initialize datasets
    training_dataset = SemanticKittiDataset(config, set='training',
                                            balance_classes=False)
    test_dataset = SemanticKittiDataset(config, set='validation',
                                         balance_classes=False)

    # Initialize samplers
    training_sampler = SemanticKittiSampler(training_dataset)
    test_sampler = SemanticKittiSampler(test_dataset)

    # Initialize the dataloader
    training_loader = DataLoader(training_dataset,
                                  batch_size=1,
                                  sampler=training_sampler,
                                  collate_fn=SemanticKittiCollate,
                                  num_workers=config.input_threads,
                                  pin_memory=True)
    
    #write_ply("/home/willalbert20/Documents/out/batch.ply", [batch.points[0].numpy(), batch.labels.numpy().astype(np.int32)], ['x', 'y', 'z', 'labels'])

        
    
    test_loader = DataLoader(test_dataset,
                              batch_size=1,
                              sampler=test_sampler,
                              collate_fn=SemanticKittiCollate,
                              num_workers=config.input_threads,
                              pin_memory=True)
    
    # batch=next(iter(training_loader))
    
    # a = batch.points[0].cuda()
    
    # Calibrate max_in_point value
    # training_sampler.calib_max_in(config, training_loader, verbose=True)
    # test_sampler.calib_max_in(config, test_loader, verbose=True)

    # # Calibrate samplers
    # training_sampler.calibration(training_loader, verbose=True)
    # test_sampler.calibration(test_loader, verbose=True)

    # debug_timing(training_dataset, training_loader)
    # debug_timing(test_dataset, test_loader)
    # debug_class_w(training_dataset, training_loader)

    # print('\nModel Preparation')
    # print('*****************')

    # Define network model
    t1 = time.time()
    net = KPFCNN(config, training_dataset.label_values, training_dataset.ignored_labels)

    # debug = False
    # if debug:
    #     print('\n*************************************\n')
    #     print(net)
    #     print('\n*************************************\n')
    #     for param in net.parameters():
    #         if param.requires_grad:
    #             print(param.shape)
    #     print('\n*************************************\n')
    #     print("Model size %i" % sum(param.numel() for param in net.parameters() if param.requires_grad))
    #     print('\n*************************************\n')

    # Define a trainer class
    trainer = ModelTrainer(net, config, chkp_path=chosen_chkp)
    print('Done in {:.2f}s\n'.format(time.time() - t1))

    print('\nStart training')
    print('**************')
    
    # Training    
    trainer.train(net, training_loader, test_loader, config)
    
    wandb.finish()
    
    os.system("nvidia-settings -a \"[gpu:0]/GPUFanControlState=1\" -a \"[fan:0]/GPUTargetFanSpeed=30\" -a \"[fan:1]/GPUTargetFanSpeed=30\"")
    os.system("nvidia-settings -a \"[gpu:0]/GPUFanControlState=1\" -a \"[fan:0]/GPUTargetFanSpeed=30\" -a \"[fan:1]/GPUTargetFanSpeed=30\"")
    
    print('DONE')
    # os.kill(os.getpid(), signal.SIGINT)
