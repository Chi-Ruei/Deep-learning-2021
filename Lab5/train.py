from __future__ import unicode_literals, print_function, division
import random
import torch
import torch.nn as nn
from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
SOS_token=0
EOS_token=1

def compute_bleu(output, reference):
    """
    :param output: The word generated by your model
    :param reference: The target word
    :return:
    """
    cc = SmoothingFunction()
    if len(reference) == 3:
        weights = (0.33,0.33,0.33)
    else:
        weights = (0.25,0.25,0.25,0.25)
    return sentence_bleu([reference], output,weights=weights,smoothing_function=cc.method1)

def loss_function(predict_distribution,predict_output_length,target,mu,logvar):
    """
    :param predict_distribution: (target_length,28) tensor
    :param predict_output_length:           (may contain EOS)
    :param target: (target_length) tensor   (contain EOS)
    :param mu: mean in VAE
    :param logvar: logvariance in VAE
    :return: CrossEntropy loss, KL divergence loss
    """
    Criterion=nn.CrossEntropyLoss()
    CEloss=Criterion(predict_distribution[:predict_output_length],target[:predict_output_length])

    # KL(N(mu,variance)||N(0,1))
    KLloss = -0.5 * torch.sum(1 + logvar - mu**2 - logvar.exp())
    return CEloss, KLloss


def train(vae,loader_train,optimizer,teacher_forcing_ratio,kl_weight,tensor2string):
    """train 1 epoch
    :param vae: model
    :param loader_train: loader_train
    :param optimizer: sgd optimizer
    :param tensor2string: function(tensor){ return string }  (cutoff EOS automatically)
    :returns: CEloss, KLloss, BLEUscore
    """
    vae.train()
    total_CEloss=0
    total_KLloss=0
    total_BLEUscore=0
    for word_tensor,tense_tensor in loader_train:
        optimizer.zero_grad()
        word_tensor,tense_tensor=word_tensor[0],tense_tensor[0]
        word_tensor,tense_tensor=word_tensor.to(device),tense_tensor.to(device)

        # init hidden_state
        h0 = vae.encoder.init_h0(vae.hidden_size - vae.conditional_size)
        c = vae.tense_embedding(tense_tensor).view(1, 1, -1)
        encoder_hidden_state = torch.cat((h0, c), dim=-1)
        # init cell_state
        encoder_cell_state = vae.encoder.init_c0()

        # forwarding one word by calling VAE Model forwarding
        """set teacher forcing ratio = 
        """
        use_teacher_forcing=True if random.random()<teacher_forcing_ratio else False
        predict_output,predict_distribution,mean,logvar=vae(word_tensor,encoder_hidden_state,encoder_cell_state,c,use_teacher_forcing)
        CEloss,KLloss = loss_function(predict_distribution,predict_output.size(0),word_tensor.view(-1),mean,logvar)
        loss = CEloss + kl_weight * KLloss
        total_CEloss+=CEloss.item()
        total_KLloss+=KLloss.item()
        predict,target=tensor2string(predict_output),tensor2string(word_tensor)
        total_BLEUscore+=compute_bleu(predict,target)

        #update
        loss.backward()
        optimizer.step()

    return total_CEloss/len(loader_train), total_KLloss/len(loader_train), total_BLEUscore/len(loader_train)


def evaluate(vae,loader_test,tensor2string):
    """
    :param tensor2string: function(tensor){ return string }  (cutoff EOS automatically)
    :return: [[input,target,predict],[input,target,predict]...], BLEUscore
    """
    vae.eval()
    re=[]
    total_BLEUscore=0
    with torch.no_grad():
        for in_word_tensor,in_tense_tensor,tar_word_tensor,tar_tense_tensor in loader_test:
            in_word_tensor,in_tense_tensor=in_word_tensor[0].to(device),in_tense_tensor[0].to(device)
            tar_word_tensor,tar_tense_tensor=tar_word_tensor[0].to(device),tar_tense_tensor[0].to(device)

            # init hidden_state
            h0 = vae.encoder.init_h0(vae.hidden_size - vae.conditional_size)
            in_c = vae.tense_embedding(in_tense_tensor).view(1, 1, -1)
            encoder_hidden_state = torch.cat((h0, in_c), dim=-1)
            # init cell_state
            encoder_cell_state = vae.encoder.init_c0()

            # forwarding one word by calling VAE Mode inference
            tar_c=vae.tense_embedding(tar_tense_tensor).view(1,1,-1)
            predict_output=vae.inference(in_word_tensor,encoder_hidden_state,encoder_cell_state,tar_c)
            target_word=tensor2string(tar_word_tensor)
            predict_word=tensor2string(predict_output)
            re.append([tensor2string(in_word_tensor),target_word,predict_word])
            total_BLEUscore+=compute_bleu(predict_word,target_word)

    return re, total_BLEUscore/len(loader_test)

def generateWord(vae,latent_size,tensor2string):
    vae.eval()
    re=[]
    with torch.no_grad():
        for i in range(100):
            latent = torch.randn(1, 1, latent_size).to(device)
            tmp = []
            for tense in range(4):
                word = tensor2string(vae.generate(latent, tense))
                tmp.append(word)

            re.append(tmp)
    return re