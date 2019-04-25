import torch 
import matplotlib
matplotlib.use("agg")
import matplotlib.pyplot as plt
from utils import load_checkpoint
from train import preprocess_images, denormalize_img
from torchvision.transforms.functional import to_tensor
import numpy as np
import utils
import cv2
import os
import glob
from scripts.anonymize_dataset import anonymize_single_bbox
from dataset_tools.utils import expand_bounding_box, is_keypoint_within_bbox
#from dataset_tool_new import expand_bounding_box
from scripts.utils import init_generator, get_model_name, image_to_numpy
from SFD_pytorch.wider_eval_pytorch import detect_and_supress
from detectron_scripts.infer_simple_v2 import predict_keypoint
from options import print_options
from dataloaders_v2 import cut_bounding_box
from scripts.utils import draw_bboxes, draw_keypoints



if __name__ == "__main__":
    model_name = get_model_name()
    ckpt_path = os.path.join("checkpoints", model_name)
    ckpt = load_checkpoint(ckpt_path)
    source_dir = os.path.join("test_examples", "real_images_test", "frames")
    savedir = os.path.join("test_examples", "real_images_test", "frames_out")
    os.makedirs(savedir, exist_ok=True)
    pose_size = ckpt["pose_size"]
    # pose_size = 5 if ckpt["dataset"] == "ffhq" else 7
    g = init_generator(ckpt)
    imsize = ckpt["current_imsize"]
    g.eval()
    endings = ["*.jpg", "*.jpeg", "*.png"]
    image_paths = []
    for e in endings:
        image_paths += glob.glob(os.path.join(source_dir, e))
    for impath in image_paths:
        #print(impath)
        #if "selfie" not in impath: continue
        #if "selfie3" in impath: continue
        #if "_" not in impath.split("/")[-1]: continue
        im = cv2.imread(impath) # BGR
        keypoints = predict_keypoint(impath)
        #print(keypoints)
        if len(keypoints) == 0:
            continue 
        keypoints = keypoints[:, :2, :pose_size]
        bounding_boxes = detect_and_supress(im)
        orig_keypoints = keypoints.copy()
        im = im[:, :, ::-1] # BGR to RGB
        new_image = im.copy()
        replaced_mask = np.ones_like(new_image).astype("bool")
        bounding_box_replaced = []
        for idx, bbox in enumerate(bounding_boxes):
            to_generate = im.copy()
            x0, y0, x1, y1 = bbox
            width = x1 - x0
            height = y1 - y0
            try:
                x0_, y0_, width_, height_ = expand_bounding_box(x0,
                                                                y0,
                                                                x1,
                                                                y1,
                                                                0.35,
                                                                im.shape)
            except AssertionError:
                print("Could not process image", impath, idx)
                continue
            assert width_ == height_
            x1_, y1_ = x0_ + width_, y0_ + height_
            orig = new_image[y0_:y1_, x0_:x1_, :].copy()
            result = anonymize_single_bbox(new_image, keypoints, bbox, g, imsize)
            if result is None:
                continue
            to_generate, final_keypoint = result 
            x0, x1 = x0 - x0_, x1 - x0_
            y0, y1 = y0 - y0_, y1 - y0_

            bounding_box_replaced.append(bbox)
            
            final_keypoint[0, :] -= x0_
            final_keypoint[1, :] -= y0_
            final_keypoint = np.array([final_keypoint[j, i] for i in range(final_keypoint.shape[1]) for j in range(2)])

            debug_image = cut_bounding_box(orig.copy(), [x0, y0, x1, y1])# (image_to_numpy(debug_image) * 255).astype("uint8")[0]
            #orig = cv2.resize(orig, (imsize, imsize), interpolation=cv2.INTER_AREA)
            debug_image = np.concatenate((orig, debug_image, to_generate), axis=1)
            plt.clf()
            plt.imshow(debug_image)

            X = final_keypoint[range(0, len(final_keypoint), 2)]
            Y = final_keypoint[range(1, len(final_keypoint), 2)]
            

            plt.plot( X, Y, "o")
                
            debug_dir = os.path.join(savedir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            debug_path = os.path.join(debug_dir, "{}_{}.jpg".format(os.path.basename(impath).split(".")[0], idx))
            debug_path2 = os.path.join(debug_dir, "{}_{}_no_mark.jpg".format(os.path.basename(impath).split(".")[0], idx))
            plt.imsave(debug_path2, debug_image)
            #plt.legend()
            plt.ylim([orig.shape[0], 0])
            plt.xlim([0, orig.shape[0]*3+orig.shape[0]//2])
            plt.savefig(debug_path)
            replaced_mask_cut = replaced_mask[y0_:y0_+height_, x0_:x0_+width_]
            
            to_replace = new_image[y0_:y0_+height_, x0_:x0_+width_]
            to_replace[replaced_mask_cut] = to_generate[replaced_mask_cut]

            new_image[y0_:y0_+height_, x0_:x0_+width_] = to_replace
            
            x0_m, y0_m, x1_m, y1_m = bbox
            replaced_mask[y0_m:y1_m, x0_m:x1_m, :] = 0
            

        imname = os.path.basename(impath).split(".")[0]

        save_path = os.path.join(savedir, "{}_generated.jpg".format(imname))
        plt.imsave(save_path, new_image)
        print("Image saved to:", save_path)

        save_path = os.path.join(savedir, "{}_marked.jpg".format(imname))
        image2 = draw_bboxes(new_image, bounding_box_replaced, (255, 0, 0))
        plt.imsave(save_path, image2)
        


        # Save detected boxes
        save_path = imname.split(".")[0]
        save_path = "{}_detected.jpg".format(save_path)
        save_path = os.path.join(savedir, save_path)
        image = draw_bboxes(im, bounding_boxes, (255, 0, 0))
        for idx, bbox in enumerate(bounding_boxes):
            x0, y0, x1, y1 = bbox
            width = x1 - x0 
            height = y1 - y0
            try:
                x0, y0, width, height = expand_bounding_box(x0, y0, x1, y1, 0.35, image.shape)
            except AssertionError:
                continue
            bounding_boxes[idx] = [x0, y0, x0+width, y0+height]
        draw_keypoints(image, orig_keypoints, (0, 0, 255))
        image = draw_bboxes(image, bounding_boxes, (0, 0, 255))

        plt.imsave(save_path, image)
