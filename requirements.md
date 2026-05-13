Yêu cầu tính năng:
1. Thu thập tỉ giá tiền tệ so với VND qua API bên ngoài (VD: Exchange Rate API)
2. Stream lên dashboard ở frontend bằng websocket
3. Dùng model máy học để dự báo tỉ giá trong tương lai
4. Dùng data tỉ giá mới để huấn luyện lại model máy học và đảm bảo model đang được sử dụng là model tốt nhất trong các model đã huấn luyện
5. Cho phép user trao đổi giữa các loại tiền tệ và nạp thêm tiền (tiền giả lập để làm đồ án)
6. Thu thập thông tin các tour du lịch ở các nước liên quan đến loại tiền tệ mà ứng dụng phục vụ
7. Hiển thị thông tin các tour du lịch ở phần tiền tệ tương ứng và redirect đến website hỗ trợ tour du lịch đó khi user nhấn vào
8. Cho phép user tạo tài khoản và đăng nhập, quên mật khẩu
9. Dựa trên thuộc tính của user, nếu user premium thì cho phép xem dự đoán tỉ giá của các model, user bình thường không thể xem
10. Cho phép user tự nâng cấp lên gói premium trong ứng dụng (không tích hợp payment thật, dùng tiền giả lập trong hệ thống để thanh toán)