from .resnet import ResNet
import paddle

class DANet(paddle.nn.Layer):
    def __init__(self,name_scope,out_chs=20,in_chs=2048,inter_chs=512):
        super(DANet,self).__init__(name_scope)
        name_scope = self.full_name()
        self.in_chs = in_chs
        self.out_chs = out_chs
        self.inter_chs = inter_chs if inter_chs else in_chs


        # self.backbone = ResNet(50)
        self.backbone = ResNet(101)
        self.conv5p = paddle.nn.Sequential(
            paddle.nn.Conv2D(in_channels=self.in_chs, out_channels=self.inter_chs, kernel_size=3, padding=1),
            paddle.nn.BatchNorm2D(self.inter_chs,act='relu'),
        )
        self.conv5c = paddle.nn.Sequential(
            paddle.nn.Conv2D(in_channels=self.in_chs, out_channels=self.inter_chs, kernel_size=3, padding=1),
            paddle.nn.BatchNorm2D(self.inter_chs,act='relu'),
        )

        self.sp = PAM_module(self.inter_chs)
        self.sc = CAM_module(self.inter_chs)

        self.conv6p = paddle.nn.Sequential(
            paddle.nn.Conv2D(in_channels=self.inter_chs, out_channels=self.inter_chs, kernel_size=3, padding=1),
            paddle.nn.BatchNorm2D(self.inter_chs,act='relu'),
        )
        self.conv6c = paddle.nn.Sequential(
            paddle.nn.Conv2D(in_channels=self.inter_chs, out_channels=self.inter_chs, kernel_size=3, padding=1),
            paddle.nn.BatchNorm(self.inter_chs,act='relu'),
        )

        self.conv7p = paddle.nn.Sequential(
            paddle.nn.Dropout2D(0.1),
            paddle.nn.Conv2D(in_channels=self.inter_chs, out_channels=self.out_chs, kernel_size=1),
        )
        self.conv7c = paddle.nn.Sequential(
            paddle.nn.Dropout2D(0.1),
            paddle.nn.Conv2D(in_channels=self.inter_chs, out_channels=self.out_chs, kernel_size=1),
        )
        self.conv7pc = paddle.nn.Sequential(
            paddle.nn.Dropout2D(0.1),
            paddle.nn.Conv2D(in_channels=self.inter_chs, out_channels=self.out_chs, kernel_size=1),
        )

    def forward(self,x):

        feature = self.backbone(x)
        # print(feature.shape)
        p_f = self.conv5p(feature)
        p_f = self.sp(p_f)
        p_f = self.conv6p(p_f)
        p_out = self.conv7p(p_f)

        c_f = self.conv5c(feature)
        c_f = self.sc(c_f)
        c_f = self.conv6c(c_f)
        c_out = self.conv7c(c_f)

        sum_f = p_f+c_f
        sum_out = self.conv7pc(sum_f)

        p_out = paddle.reshape(p_out,out_shape=x.shape[2:])
        c_out = paddle.reshape(c_out,out_shape=x.shape[2:])
        sum_out = paddle.reshape(sum_out,out_shape=x.shape[2:])


        # print('p_out.shape',p_out.shape)
        # print('c_out.shape',c_out.shape)
        # print('sum_out.shape',sum_out.shape)

        return [p_out, c_out, sum_out]
        # return sum_out

class PAM_module(paddle.nn.Layer):
    def __init__(self,in_chs,inter_chs=None):
        super(PAM_module,self).__init__()
        self.in_chs = in_chs
        self.inter_chs = inter_chs if inter_chs else in_chs
        self.conv_query = paddle.nn.Conv2D(in_channels=self.in_chs,out_channels=self.inter_chs,kernel_size=1)
        self.conv_key = paddle.nn.Conv2D(in_channels=self.in_chs,out_channels=self.inter_chs,kernel_size=1)
        self.conv_value = paddle.nn.Conv2D(in_channels=self.in_chs,out_channels=self.inter_chs,kernel_size=1)
        self.gamma = paddle.create_parameter([1], dtype='float32')
    
    def forward(self,x):
        b,c,h,w = x.shape

        f_query = self.conv_query(x)
        f_query = paddle.reshape(x=f_query,shape=(b, -1, h*w))
        f_query = paddle.transpose(f_query,(0, 2, 1)) 

        f_key = self.conv_key(x)
        f_key = paddle.reshape(x=f_key,shape=(b, -1, h*w))

        f_value = self.conv_value(x)
        f_value = paddle.reshape(x=f_value,shape=(b, -1, h*w))
        f_value = paddle.transpose(f_value,(0, 2, 1)) 


        f_similarity = paddle.bmm(f_query, f_key)                        # [h*w, h*w]
        f_similarity = paddle.nn.functional.softmax(x=f_similarity)
        f_similarity = paddle.transpose(f_similarity,(0, 2, 1))

        f_attention = paddle.bmm(f_similarity, f_value)                        # [h*w, c]
        f_attention = paddle.reshape(x=f_attention,shape=(b,c,h,w))

        out = self.gamma*f_attention + x
        return out

class CAM_module(paddle.nn.Layer):
    def __init__(self,in_chs,inter_chs=None):
        super(CAM_module,self).__init__()
        self.in_chs = in_chs
        self.inter_chs = inter_chs if inter_chs else in_chs
        self.gamma = paddle.create_parameter([1], dtype='float32')

    def forward(self,x):
        b,c,h,w = x.shape

        f_query = paddle.reshape(x=x,shape=(b, -1, h*w))
        f_key = paddle.reshape(x=x,shape=(b, -1, h*w))
        f_key = paddle.transpose(f_key,(0, 2, 1)) 
        f_value = paddle.reshape(x=x,shape=(b, -1, h*w))

        f_similarity = paddle.bmm(f_query, f_key)                        # [h*w, h*w]
        f_similarity_max = paddle.max(x=f_similarity, axis=-1, keepdim=True)
        f_similarity_max_reshape = paddle.expand_as(x=f_similarity_max,y=f_similarity)
        f_similarity = f_similarity_max_reshape-f_similarity

        f_similarity = paddle.nn.functional.softmax(x=f_similarity)
        f_similarity = paddle.transpose(f_similarity,(0, 2, 1)) 

        f_attention = paddle.bmm(f_similarity,f_value)                        # [h*w, c]
        f_attention = paddle.reshape(x=f_attention,shape=(b,c,h,w))

        out = self.gamma*f_attention + x
        return out












