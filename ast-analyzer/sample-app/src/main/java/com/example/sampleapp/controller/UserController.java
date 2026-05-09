package com.example.sampleapp.controller;

import com.example.sampleapp.model.User;
import com.example.sampleapp.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import javax.servlet.http.HttpSession;

@Controller
@RequestMapping("/user")
public class UserController {

    @Autowired
    private UserService userService;

    @GetMapping("/login")
    public String loginForm() {
        return "user/login";
    }

    @PostMapping("/login")
    public String login(@RequestParam String username,
                        @RequestParam String password,
                        HttpSession session,
                        Model model) {
        User user = userService.login(username, password);
        if (user == null) {
            model.addAttribute("error", "ユーザー名またはパスワードが正しくありません");
            return "user/login";
        }
        session.setAttribute("loginUser", user);
        return "redirect:/product/list";
    }

    @GetMapping("/logout")
    public String logout(HttpSession session) {
        session.invalidate();
        return "redirect:/user/login";
    }

    @GetMapping("/mypage")
    public String mypage(HttpSession session, Model model) {
        User loginUser = (User) session.getAttribute("loginUser");
        if (loginUser == null) {
            return "redirect:/user/login";
        }
        User user = userService.getUserById(loginUser.getId());
        model.addAttribute("user", user);
        return "user/mypage";
    }

    @GetMapping("/register")
    public String registerForm(Model model) {
        model.addAttribute("user", new User());
        return "user/register";
    }

    @PostMapping("/register")
    public String register(@ModelAttribute User user) {
        userService.registerUser(user);
        return "redirect:/user/login";
    }

    @PostMapping("/update")
    public String update(@ModelAttribute User user, HttpSession session) {
        userService.updateUser(user);
        session.setAttribute("loginUser", user);
        return "redirect:/user/mypage";
    }
}
